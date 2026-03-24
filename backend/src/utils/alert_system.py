import os
import tempfile
import threading
import time

from gtts import gTTS
import pygame


class AlertSystem:
    def __init__(self, config):
        self.config = config
        self.alert_cooldown = config['logging']['alert_cooldown']
        self.last_alert_time = {}

        # Audio availability flag
        self.audio_enabled = False

        # Try to initialize pygame mixer safely
        try:
            pygame.mixer.init()
            self.audio_enabled = True
        except Exception as e:
            print("[WARNING] Audio output not available. Audio alerts disabled.")
            print("Reason:", e)
            self.audio_enabled = False

        # Alert messages database
        self.alerts = {
            "FACE_DISAPPEARED": "Please look at the screen",
            "FACE_REAPPEARED": "Thank you for looking at the screen",
            "MULTIPLE_FACES": "We detected multiple people",
            "OBJECT_DETECTED": "Unauthorized object detected",
            "GAZE_AWAY": "Please focus on your screen",
            "MOUTH_MOVING": "Please maintain silence during exam",
            "SPEECH_VIOLATION": "Speaking during exam is not allowed",
            "VOICE_DETECTED": "We detected voice. Please maintain silence during the exam",
        }

    def _can_alert(self, alert_type):
        """Check if enough time has passed since last alert"""
        current_time = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        return (current_time - last_time) >= self.alert_cooldown

    def speak_alert(self, alert_type):
        """Convert text to speech and play it safely"""

        # If audio is disabled, silently skip
        if not self.audio_enabled:
            return

        if not self._can_alert(alert_type):
            return

        self.last_alert_time[alert_type] = time.time()

        def _play_audio():
            temp_path = None
            try:
                if alert_type not in self.alerts:
                    return

                # Generate speech
                tts = gTTS(text=self.alerts[alert_type], lang='en')

                # Save temporary audio file
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as fp:
                    temp_path = fp.name
                    tts.save(temp_path)

                # Play audio
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()

                # Wait until playback finishes
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)

            except Exception as e:
                print("[WARNING] Audio alert failed:", e)

            finally:
                # Cleanup temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        # Run in separate thread to avoid blocking main loop
        threading.Thread(target=_play_audio, daemon=True).start()
