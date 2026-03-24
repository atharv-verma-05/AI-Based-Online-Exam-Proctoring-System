# AI-based online exam proctoring system with cheating probability & explainability


An AI-based online exam proctoring system that detects cheating behavior in real time using computer vision and generates a cheating probability score with explainability.

## Features
- Face detection
- Eye gaze tracking
- Mouth movement detection
- Object (phone/book) detection
- Multiple face detection
- Cheating probability (0–100%)
- Explainable AI: why the score is high
- Screen & webcam recording
- Automated report generation

## Tech Stack
- Python 3.10
- OpenCV
- MediaPipe
- PyTorch
- Ultralytics YOLO
- Flask (optional dashboard)

## How to Run
```bash
cd proctoring
venv\Scripts\activate
python src/main.py
