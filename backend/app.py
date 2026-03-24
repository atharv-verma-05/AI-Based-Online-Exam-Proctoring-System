"""
Exam Proctoring System - Backend API Server
Comprehensive Flask REST API for the exam cheating detection system.
"""

import os
import sys
import json
import yaml
import glob
import cv2
import threading
import time
import numpy as np
from datetime import datetime
from flask import Flask, jsonify, request, send_file, send_from_directory, Response
from flask_cors import CORS

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

def load_config():
    config_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def save_config(config_data):
    config_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)


# ─────────────────────────────────────────────
# Session State (in-memory for this server)
# ─────────────────────────────────────────────

session_state = {
    'active': False,
    'started_at': None,
    'student': None,
    'violation_count': 0,
    'alert_count': 0,
    'current_stats': {
        'face_detected': True,
        'gaze_direction': 'Center',
        'eyes_open': True,
        'eye_ratio': 0.3,
        'mouth_moving': False,
        'multiple_faces': False,
        'objects_detected': False,
        'cheating_probability': 0,
        'cheating_reasons': [],
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
}


# ─────────────────────────────────────────────
# Live Exam Detection Engine
# ─────────────────────────────────────────────

exam_engine = {
    'running': False,
    'thread': None,
    'cap': None,
    'lock': threading.Lock(),
    'current_frame': None,  # Latest annotated JPEG frame
    'detectors': None,
    'cheating_calculator': None,
    'violation_logger': None,
    'alert_logger': None,
}


def _init_detectors(config):
    """Initialize all detection modules."""
    try:
        from detection.face_detection import FaceDetector
        from detection.eye_tracking import EyeTracker
        from detection.mouth_detection import MouthMonitor
        from detection.multi_face import MultiFaceDetector
        from utils.cheating_probability import CheatingProbabilityCalculator
        from utils.logging import AlertLogger
        from utils.violation_logger import ViolationLogger

        detectors = {
            'face': FaceDetector(config),
            'eyes': EyeTracker(config),
            'mouth': MouthMonitor(config),
            'multi_face': MultiFaceDetector(config),
        }

        # Try to load object detector (needs YOLO model file)
        try:
            from detection.object_detection import ObjectDetector
            detectors['objects'] = ObjectDetector(config)
        except Exception as e:
            print(f"[WARN] Object detection unavailable: {e}")
            detectors['objects'] = None

        alert_logger = AlertLogger(config)
        violation_logger = ViolationLogger(config)
        calculator = CheatingProbabilityCalculator(window_size=30)

        # Set alert loggers on detectors
        for det in detectors.values():
            if det and hasattr(det, 'set_alert_logger'):
                det.set_alert_logger(alert_logger)

        return detectors, calculator, alert_logger, violation_logger
    except Exception as e:
        print(f"[ERROR] Failed to init detectors: {e}")
        return None, None, None, None


def _detection_loop():
    """Background thread: read webcam, run detectors, update stats, encode frame."""
    config = load_config()
    source = config.get('video', {}).get('source', 0)
    resolution = config.get('video', {}).get('resolution', [1280, 720])

    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    exam_engine['cap'] = cap

    if not cap.isOpened():
        print("[ERROR] Cannot open webcam")
        exam_engine['running'] = False
        return

    detectors, calculator, alert_logger, violation_logger = _init_detectors(config)
    if detectors is None:
        cap.release()
        exam_engine['running'] = False
        return

    exam_engine['detectors'] = detectors
    exam_engine['cheating_calculator'] = calculator
    exam_engine['alert_logger'] = alert_logger
    exam_engine['violation_logger'] = violation_logger

    print("[INFO] Detection engine started")

    while exam_engine['running']:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        # ── Run detectors ──
        results = {
            'face_present': False,
            'gaze_direction': 'Center',
            'eye_ratio': 0.3,
            'mouth_moving': False,
            'multiple_faces': False,
            'objects_detected': False,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            results['face_present'] = detectors['face'].detect_face(frame)
        except Exception:
            pass

        try:
            results['gaze_direction'], results['eye_ratio'] = detectors['eyes'].track_eyes(frame)
        except Exception:
            pass

        try:
            results['mouth_moving'] = detectors['mouth'].monitor_mouth(frame)
        except Exception:
            pass

        try:
            results['multiple_faces'] = detectors['multi_face'].detect_multiple_faces(frame)
        except Exception:
            pass

        if detectors.get('objects'):
            try:
                results['objects_detected'] = detectors['objects'].detect_objects(frame)
            except Exception:
                pass

        # ── Cheating probability ──
        cheating_probability, reasons = calculator.update(results)
        results['cheating_probability'] = cheating_probability
        results['cheating_reasons'] = reasons

        # ── Update session stats ──
        session_state['current_stats'] = {
            'face_detected': results['face_present'],
            'gaze_direction': results['gaze_direction'].capitalize(),
            'eyes_open': results['eye_ratio'] > 0.25,
            'eye_ratio': round(results['eye_ratio'], 3),
            'mouth_moving': results['mouth_moving'],
            'multiple_faces': results['multiple_faces'],
            'objects_detected': results['objects_detected'],
            'cheating_probability': cheating_probability,
            'cheating_reasons': reasons,
            'timestamp': results['timestamp']
        }

        # ── Log violations ──
        violation_type = None
        if not results['face_present']:
            violation_type = 'FACE_DISAPPEARED'
        elif results['multiple_faces']:
            violation_type = 'MULTIPLE_FACES'
        elif results['objects_detected']:
            violation_type = 'OBJECT_DETECTED'
        elif results['mouth_moving']:
            violation_type = 'MOUTH_MOVING'

        if violation_type:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            violation_logger.log_violation(violation_type, ts, {
                'cheating_probability': cheating_probability,
                'cheating_reasons': reasons
            })
            session_state['violation_count'] = session_state.get('violation_count', 0) + 1

        # ── Draw overlays on the frame ──
        annotated = _annotate_frame(frame, results, cheating_probability, reasons)

        # ── Encode as JPEG for streaming ──
        _, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with exam_engine['lock']:
            exam_engine['current_frame'] = jpeg.tobytes()

        time.sleep(0.03)  # ~30 fps cap

    # Cleanup
    cap.release()
    exam_engine['cap'] = None
    exam_engine['current_frame'] = None
    print("[INFO] Detection engine stopped")


def _annotate_frame(frame, results, prob, reasons):
    """Draw detection status overlays on the video frame."""
    h, w = frame.shape[:2]

    # Semi-transparent overlay bar at top
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 44), (30, 30, 30), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)

    # Status text
    face_text = 'Face: Present' if results['face_present'] else 'Face: ABSENT'
    face_color = (120, 255, 120) if results['face_present'] else (100, 100, 255)
    cv2.putText(frame, face_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, face_color, 1, cv2.LINE_AA)

    gaze_text = f"Gaze: {results['gaze_direction']}"
    cv2.putText(frame, gaze_text, (200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    mouth_text = 'Mouth: MOVING' if results['mouth_moving'] else 'Mouth: Still'
    mouth_color = (100, 200, 255) if results['mouth_moving'] else (200, 200, 200)
    cv2.putText(frame, mouth_text, (380, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, mouth_color, 1, cv2.LINE_AA)

    # Cheating probability bar at bottom
    bar_y = h - 40
    bar_w = int((prob / 100) * (w - 20))
    color = (120, 255, 120) if prob < 30 else (100, 200, 255) if prob < 60 else (100, 100, 255)

    cv2.rectangle(frame, (10, bar_y), (w - 10, bar_y + 22), (50, 50, 50), -1)
    if bar_w > 0:
        cv2.rectangle(frame, (10, bar_y), (10 + bar_w, bar_y + 22), color, -1)
    cv2.putText(frame, f"Risk: {prob}%", (15, bar_y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # Alert badges
    if results['multiple_faces']:
        cv2.putText(frame, '! MULTIPLE FACES', (w - 260, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    if results['objects_detected']:
        cv2.putText(frame, '! OBJECT DETECTED', (w - 280, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)

    return frame


def _generate_mjpeg():
    """Generator yielding MJPEG frames for the video stream."""
    while exam_engine['running']:
        with exam_engine['lock']:
            frame_data = exam_engine['current_frame']
        if frame_data is None:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        time.sleep(0.033)  # ~30fps



# ─────────────────────────────────────────────
# Routes: Frontend Serving
# ─────────────────────────────────────────────

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# ─────────────────────────────────────────────
# Routes: System Status
# ─────────────────────────────────────────────

@app.route('/api/status')
def get_status():
    config = load_config()
    return jsonify({
        'status': 'online',
        'session_active': session_state['active'],
        'version': '1.0.0',
        'detection_modules': {
            'face_detection': True,
            'eye_tracking': True,
            'mouth_detection': True,
            'object_detection': True,
            'multi_face_detection': True,
            'audio_monitoring': config.get('detection', {}).get('audio_monitoring', {}).get('enabled', False)
        },
        'server_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# ─────────────────────────────────────────────
# Routes: Session Management
# ─────────────────────────────────────────────

@app.route('/api/session/start', methods=['POST'])
def start_session():
    if session_state['active']:
        return jsonify({'error': 'A session is already active'}), 400

    data = request.get_json() or {}
    session_state['active'] = True
    session_state['started_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_state['student'] = {
        'id': data.get('student_id', 'STUDENT_001'),
        'name': data.get('student_name', 'Unknown'),
        'exam': data.get('exam_name', 'Examination'),
        'course': data.get('course', 'N/A')
    }
    session_state['violation_count'] = 0
    session_state['alert_count'] = 0

    return jsonify({
        'message': 'Session started',
        'session': {
            'started_at': session_state['started_at'],
            'student': session_state['student']
        }
    })

@app.route('/api/session/stop', methods=['POST'])
def stop_session():
    if not session_state['active']:
        return jsonify({'error': 'No active session'}), 400

    started = session_state['started_at']
    session_state['active'] = False
    stopped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({
        'message': 'Session stopped',
        'summary': {
            'started_at': started,
            'stopped_at': stopped_at,
            'total_violations': session_state['violation_count'],
            'total_alerts': session_state['alert_count'],
            'student': session_state['student']
        }
    })

@app.route('/api/session/current')
def get_current_session():
    if not session_state['active']:
        return jsonify({'active': False})

    return jsonify({
        'active': True,
        'started_at': session_state['started_at'],
        'student': session_state['student'],
        'violation_count': session_state['violation_count'],
        'alert_count': session_state['alert_count'],
        'duration': _calculate_duration(session_state['started_at'])
    })


# ─────────────────────────────────────────────
# Routes: Live Detection Stats
# ─────────────────────────────────────────────

@app.route('/api/stats')
def get_stats():
    session_state['current_stats']['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(session_state['current_stats'])


# ─────────────────────────────────────────────
# Routes: Violations
# ─────────────────────────────────────────────

@app.route('/api/violations')
def get_violations():
    violations_file = os.path.join(BASE_DIR, 'reports', 'violations.json')

    if not os.path.exists(violations_file):
        return jsonify([])

    try:
        with open(violations_file, 'r') as f:
            violations = json.load(f)
    except (json.JSONDecodeError, IOError):
        return jsonify([])

    # Optional filtering
    vtype = request.args.get('type')
    if vtype:
        violations = [v for v in violations if v.get('type') == vtype]

    # Sort by timestamp descending (newest first)
    violations.sort(key=lambda v: v.get('timestamp', ''), reverse=True)

    return jsonify(violations)


# ─────────────────────────────────────────────
# Routes: Alerts
# ─────────────────────────────────────────────

@app.route('/api/alerts')
def get_alerts():
    log_file = os.path.join(BASE_DIR, 'logs', 'alerts.log')
    alerts = []

    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()

            limit = int(request.args.get('limit', 50))
            for line in reversed(lines[-limit:]):
                line = line.strip()
                if not line:
                    continue

                # Parse: "2024-01-15 10:30:45 - ALERT_TYPE: message"
                parts = line.split(' - ', 1)
                if len(parts) == 2:
                    timestamp = parts[0]
                    type_msg = parts[1].split(': ', 1)
                    alert_type = type_msg[0] if type_msg else 'UNKNOWN'
                    message = type_msg[1] if len(type_msg) > 1 else ''
                    alerts.append({
                        'timestamp': timestamp,
                        'type': alert_type,
                        'message': message
                    })
                else:
                    alerts.append({
                        'timestamp': '',
                        'type': 'UNKNOWN',
                        'message': line
                    })
        except IOError:
            pass

    return jsonify(alerts)


# ─────────────────────────────────────────────
# Routes: Reports
# ─────────────────────────────────────────────

@app.route('/api/reports')
def get_reports():
    reports_dir = os.path.join(BASE_DIR, 'reports', 'generated')
    reports = []

    if os.path.exists(reports_dir):
        for f in sorted(os.listdir(reports_dir), reverse=True):
            if f.endswith(('.html', '.pdf')):
                filepath = os.path.join(reports_dir, f)
                stats = os.stat(filepath)
                reports.append({
                    'filename': f,
                    'format': 'PDF' if f.endswith('.pdf') else 'HTML',
                    'size': stats.st_size,
                    'size_formatted': _format_size(stats.st_size),
                    'created_at': datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

    return jsonify(reports)

@app.route('/api/reports/<filename>')
def download_report(filename):
    reports_dir = os.path.join(BASE_DIR, 'reports', 'generated')
    filepath = os.path.join(reports_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Report not found'}), 404

    return send_file(filepath, as_attachment=True)


# ─────────────────────────────────────────────
# Routes: Recordings
# ─────────────────────────────────────────────

@app.route('/api/recordings')
def get_recordings():
    recordings_dir = os.path.join(BASE_DIR, 'recordings')
    recordings = []

    if os.path.exists(recordings_dir):
        for f in sorted(os.listdir(recordings_dir), reverse=True):
            if f.endswith(('.mp4', '.avi', '.mkv')):
                filepath = os.path.join(recordings_dir, f)
                stats = os.stat(filepath)
                rec_type = 'screen' if f.startswith('screen_') else 'webcam'
                recordings.append({
                    'filename': f,
                    'type': rec_type,
                    'size': stats.st_size,
                    'size_formatted': _format_size(stats.st_size),
                    'created_at': datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

    return jsonify(recordings)

@app.route('/api/recordings/<filename>')
def download_recording(filename):
    recordings_dir = os.path.join(BASE_DIR, 'recordings')
    filepath = os.path.join(recordings_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Recording not found'}), 404

    return send_file(filepath, as_attachment=True)


# ─────────────────────────────────────────────
# Routes: Configuration
# ─────────────────────────────────────────────

@app.route('/api/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify(config)

@app.route('/api/config', methods=['PUT'])
def update_config():
    try:
        new_config = request.get_json()
        if not new_config:
            return jsonify({'error': 'No configuration data provided'}), 400

        save_config(new_config)
        return jsonify({'message': 'Configuration updated successfully', 'config': new_config})
    except Exception as e:
        return jsonify({'error': f'Failed to update config: {str(e)}'}), 500


# ─────────────────────────────────────────────
# Routes: Violation Screenshots
# ─────────────────────────────────────────────

@app.route('/api/violation-captures')
def get_violation_captures():
    captures_dir = os.path.join(BASE_DIR, 'reports', 'violation_captures')
    captures = []

    if os.path.exists(captures_dir):
        for f in sorted(os.listdir(captures_dir), reverse=True):
            if f.endswith(('.jpg', '.png')):
                filepath = os.path.join(captures_dir, f)
                stats = os.stat(filepath)
                # Parse violation type from filename
                parts = f.rsplit('_', 3)
                vtype = parts[0] if parts else 'UNKNOWN'
                captures.append({
                    'filename': f,
                    'type': vtype,
                    'size_formatted': _format_size(stats.st_size),
                    'created_at': datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'url': f'/api/violation-captures/{f}'
                })

    return jsonify(captures)

@app.route('/api/violation-captures/<filename>')
def get_violation_capture(filename):
    captures_dir = os.path.join(BASE_DIR, 'reports', 'violation_captures')
    filepath = os.path.join(captures_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Capture not found'}), 404

    return send_file(filepath)


# ─────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────

def _calculate_duration(started_at_str):
    try:
        started = datetime.strptime(started_at_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - started
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception:
        return "00:00:00"

def _format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# ─────────────────────────────────────────────
# Routes: Live Exam (start/stop webcam + detectors)
# ─────────────────────────────────────────────

@app.route('/api/exam/start', methods=['POST'])
def start_exam():
    if exam_engine['running']:
        return jsonify({'error': 'Exam is already running'}), 400

    data = request.get_json() or {}
    # Also start the session
    session_state['active'] = True
    session_state['started_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_state['student'] = {
        'id': data.get('student_id', 'STUDENT_001'),
        'name': data.get('student_name', 'Unknown'),
        'exam': data.get('exam_name', 'Examination'),
        'course': data.get('course', 'N/A')
    }
    session_state['violation_count'] = 0
    session_state['alert_count'] = 0

    exam_engine['running'] = True
    t = threading.Thread(target=_detection_loop, daemon=True)
    exam_engine['thread'] = t
    t.start()

    return jsonify({'message': 'Exam started — camera and detection active'})


@app.route('/api/exam/stop', methods=['POST'])
def stop_exam():
    if not exam_engine['running']:
        return jsonify({'error': 'No exam is running'}), 400

    exam_engine['running'] = False
    if exam_engine['thread']:
        exam_engine['thread'].join(timeout=5)

    # Fully reset engine state so a new exam can start
    exam_engine['thread'] = None
    exam_engine['detectors'] = None
    exam_engine['cheating_calculator'] = None
    exam_engine['violation_logger'] = None
    exam_engine['alert_logger'] = None
    exam_engine['current_frame'] = None
    if exam_engine.get('cap') and exam_engine['cap'] is not None:
        try:
            exam_engine['cap'].release()
        except Exception:
            pass
    exam_engine['cap'] = None

    total_violations = session_state.get('violation_count', 0)
    session_state['active'] = False
    # Reset stats to defaults
    session_state['current_stats'] = {
        'face_detected': True,
        'gaze_direction': 'Center',
        'eyes_open': True,
        'eye_ratio': 0.3,
        'mouth_moving': False,
        'multiple_faces': False,
        'objects_detected': False,
        'cheating_probability': 0,
        'cheating_reasons': [],
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return jsonify({
        'message': 'Exam stopped',
        'total_violations': total_violations
    })


@app.route('/api/exam/status')
def exam_status():
    return jsonify({
        'running': exam_engine['running'],
        'session': {
            'active': session_state['active'],
            'started_at': session_state.get('started_at'),
            'student': session_state.get('student'),
            'violation_count': session_state.get('violation_count', 0),
            'duration': _calculate_duration(session_state['started_at']) if session_state.get('started_at') else '00:00:00'
        }
    })


@app.route('/api/exam/video_feed')
def video_feed():
    """MJPEG stream of the annotated webcam feed."""
    if not exam_engine.get('running'):
        return jsonify({'error': 'No exam is running'}), 400
    return Response(_generate_mjpeg(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')



# ─────────────────────────────────────────────
# Routes: Custom Exam Management
# ─────────────────────────────────────────────

EXAMS_FILE = os.path.join(BASE_DIR, 'config', 'exams.json')

def _load_exams():
    if os.path.exists(EXAMS_FILE):
        try:
            with open(EXAMS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # Default exams
    defaults = [
        {'id': 'final_cs101', 'name': 'Final Examination', 'course': 'Computer Science 101', 'duration_min': 120},
        {'id': 'midterm_math201', 'name': 'Midterm Exam', 'course': 'Mathematics 201', 'duration_min': 90},
        {'id': 'quiz_phy101', 'name': 'Quiz 1', 'course': 'Physics 101', 'duration_min': 30},
    ]
    _save_exams(defaults)
    return defaults

def _save_exams(exams):
    os.makedirs(os.path.dirname(EXAMS_FILE), exist_ok=True)
    with open(EXAMS_FILE, 'w') as f:
        json.dump(exams, f, indent=2)

@app.route('/api/exams', methods=['GET'])
def get_exams():
    return jsonify(_load_exams())

@app.route('/api/exams', methods=['POST'])
def add_exam():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    course = data.get('course', '').strip()
    duration = data.get('duration_min', 60)
    if not name:
        return jsonify({'error': 'Exam name is required'}), 400

    exams = _load_exams()
    new_id = name.lower().replace(' ', '_') + '_' + datetime.now().strftime('%H%M%S')
    exam = {'id': new_id, 'name': name, 'course': course, 'duration_min': duration}
    exams.append(exam)
    _save_exams(exams)
    return jsonify({'message': 'Exam added', 'exam': exam})

@app.route('/api/exams/<exam_id>', methods=['DELETE'])
def delete_exam(exam_id):
    exams = _load_exams()
    exams = [e for e in exams if e.get('id') != exam_id]
    _save_exams(exams)
    return jsonify({'message': 'Exam deleted'})


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == '__main__':
    # Ensure required directories exist
    os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'reports', 'generated'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'reports', 'violation_captures'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'recordings'), exist_ok=True)

    print("=" * 50)
    print("  Exam Proctoring System - API Server")
    print("  http://localhost:5001")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
