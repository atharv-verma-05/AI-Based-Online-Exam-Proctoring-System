from collections import deque

class CheatingProbabilityCalculator:
    def __init__(self, window_size=30):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)

        self.weights = {
            "FACE_DISAPPEARED": 40,
            "MULTIPLE_FACES": 50,
            "OBJECT_DETECTED": 45,
            "MOUTH_MOVING": 20,
            "GAZE_AWAY": 15
        }

    def compute_frame_score(self, results):
        score = 0
        reasons = []

        if not results["face_present"]:
            score += self.weights["FACE_DISAPPEARED"]
            reasons.append("Face not visible")

        if results["multiple_faces"]:
            score += self.weights["MULTIPLE_FACES"]
            reasons.append("Multiple faces detected")

        if results["objects_detected"]:
            score += self.weights["OBJECT_DETECTED"]
            reasons.append("Suspicious object detected")

        if results["mouth_moving"]:
            score += self.weights["MOUTH_MOVING"]
            reasons.append("Mouth movement detected")

        if results["gaze_direction"] != "Center":
            score += self.weights["GAZE_AWAY"]
            reasons.append("Looking away from screen")

        return min(score, 100), reasons

    def update(self, results):
        frame_score, reasons = self.compute_frame_score(results)
        self.history.append(frame_score)

        avg_score = int(sum(self.history) / len(self.history))

        return avg_score, reasons
