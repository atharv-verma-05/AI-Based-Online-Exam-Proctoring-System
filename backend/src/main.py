import cv2
import yaml
from datetime import datetime

from detection.face_detection import FaceDetector
from detection.eye_tracking import EyeTracker
from detection.mouth_detection import MouthMonitor
from detection.object_detection import ObjectDetector
from detection.multi_face import MultiFaceDetector

from utils.video_utils import VideoRecorder
from utils.screen_capture import ScreenRecorder
from utils.logging import AlertLogger
from utils.alert_system import AlertSystem
from utils.violation_logger import ViolationLogger
from utils.screenshot_utils import ViolationCapturer
from reporting.report_generator import ReportGenerator
from utils.cheating_probability import CheatingProbabilityCalculator


def load_config():
    with open('config/config.yaml', 'r') as f:
        return yaml.safe_load(f)


def display_detection_results(frame, results):
    y_offset = 30
    line_height = 30

    status_items = [
        f"Face: {'Present' if results['face_present'] else 'Absent'}",
        f"Gaze: {results['gaze_direction']}",
        f"Eyes: {'Open' if results['eye_ratio'] > 0.25 else 'Closed'}",
        f"Mouth: {'Moving' if results['mouth_moving'] else 'Still'}"
    ]

    alert_items = []
    if results['multiple_faces']:
        alert_items.append("Multiple Faces Detected!")
    if results['objects_detected']:
        alert_items.append("Suspicious Object Detected!")

    for item in status_items:
        cv2.putText(frame, item, (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        y_offset += line_height

    for item in alert_items:
        cv2.putText(frame, item, (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y_offset += line_height

    # ===============================
    # Cheating Probability Bar
    # ===============================
    prob = results.get("cheating_probability", 0)

    bar_x = 10
    bar_y = y_offset + 10
    bar_width = 300
    bar_height = 20

    cv2.rectangle(frame, (bar_x, bar_y),
                  (bar_x + bar_width, bar_y + bar_height),
                  (50, 50, 50), -1)

    fill_width = int((prob / 100) * bar_width)
    color = (0, 255, 0) if prob < 30 else (0, 255, 255) if prob < 60 else (0, 0, 255)

    cv2.rectangle(frame, (bar_x, bar_y),
                  (bar_x + fill_width, bar_y + bar_height),
                  color, -1)

    cv2.putText(frame, f"Cheating Probability: {prob}%",
                (bar_x, bar_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # ===============================
    # Explainability: WHY score is high
    # ===============================
    reasons = results.get("cheating_reasons", [])
    if reasons and prob >= 50:
        y_reason = bar_y + bar_height + 25
        cv2.putText(frame, "Why risk is high:",
                    (bar_x, y_reason),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 2)

        for reason in reasons[:3]:
            y_reason += 22
            cv2.putText(frame, f"- {reason}",
                        (bar_x + 10, y_reason),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 0, 255), 2)

    cv2.putText(frame, results['timestamp'],
                (frame.shape[1] - 260, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 255, 255), 2)


def main():
    config = load_config()

    alert_logger = AlertLogger(config)
    alert_system = AlertSystem(config)
    violation_logger = ViolationLogger(config)
    violation_capturer = ViolationCapturer(config)
    report_generator = ReportGenerator(config)

    # ===============================
    # Cheating Probability Calculator
    # ===============================
    cheating_calculator = CheatingProbabilityCalculator(window_size=30)

    student_info = {
        'id': 'STUDENT_001',
        'name': 'John Doe',
        'exam': 'Final Examination',
        'course': 'Computer Science 101'
    }

    video_recorder = VideoRecorder(config)
    screen_recorder = ScreenRecorder(config)

    cap = None

    try:
        if config.get('screen', {}).get('recording', False):
            screen_recorder.start_recording()

        detectors = [
            FaceDetector(config),
            EyeTracker(config),
            MouthMonitor(config),
            MultiFaceDetector(config),
            ObjectDetector(config)
        ]

        for detector in detectors:
            if hasattr(detector, 'set_alert_logger'):
                detector.set_alert_logger(alert_logger)

        video_recorder.start_recording()

        cap = cv2.VideoCapture(config['video']['source'])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config['video']['resolution'][0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config['video']['resolution'][1])

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results = {
                'face_present': False,
                'gaze_direction': 'Center',
                'eye_ratio': 0.3,
                'mouth_moving': False,
                'multiple_faces': False,
                'objects_detected': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            results['face_present'] = detectors[0].detect_face(frame)
            results['gaze_direction'], results['eye_ratio'] = detectors[1].track_eyes(frame)
            results['mouth_moving'] = detectors[2].monitor_mouth(frame)
            results['multiple_faces'] = detectors[3].detect_multiple_faces(frame)
            results['objects_detected'] = detectors[4].detect_objects(frame)

            # ===============================
            # Probability + Explainability
            # ===============================
            cheating_probability, reasons = cheating_calculator.update(results)
            results['cheating_probability'] = cheating_probability
            results['cheating_reasons'] = reasons

            # ===============================
            # Step 6: Log high risk
            # ===============================
            if cheating_probability >= 70:
                alert_logger.log_event(
                    "HIGH_CHEATING_PROBABILITY",
                    {
                        "probability": cheating_probability,
                        "reasons": reasons,
                        "timestamp": results["timestamp"]
                    }
                )

            violation_type = None
            if not results['face_present']:
                violation_type = "FACE_DISAPPEARED"
            elif results['multiple_faces']:
                violation_type = "MULTIPLE_FACES"
            elif results['objects_detected']:
                violation_type = "OBJECT_DETECTED"
            elif results['mouth_moving']:
                violation_type = "MOUTH_MOVING"

            if violation_type:
                alert_system.speak_alert(violation_type)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

                violation_capturer.capture_violation(frame, violation_type, timestamp)

                violation_logger.log_violation(
                    violation_type,
                    timestamp,
                    {
                        "cheating_probability": cheating_probability,
                        "cheating_reasons": reasons
                    }
                )

            display_detection_results(frame, results)
            video_recorder.record_frame(frame)

            cv2.imshow("Exam Proctoring", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        violations = violation_logger.get_violations()

        report_path = report_generator.generate_report(student_info, violations)
        if report_path:
            print(f"Report generated: {report_path}")
        else:
            print("Report generation skipped.")

        if config.get('screen', {}).get('recording', False):
            screen_data = screen_recorder.stop_recording()
            if screen_data:
                print(f"Screen recording saved: {screen_data.get('filename')}")

        video_data = video_recorder.stop_recording()
        if video_data:
            print(f"Webcam recording saved: {video_data.get('filename')}")

        if cap and cap.isOpened():
            cap.release()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
