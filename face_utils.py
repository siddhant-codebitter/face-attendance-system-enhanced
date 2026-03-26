import cv2
import numpy as np
import os
from datetime import datetime
from models import Student, AttendanceRecord, AttendanceSession, db

FACES_DIR = "student_faces"
TRAINER_FILE = "trainer.yml"
os.makedirs(FACES_DIR, exist_ok=True)

face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

def train_model():
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    image_paths = [os.path.join(FACES_DIR, f) for f in os.listdir(FACES_DIR) if f.endswith('.jpg')]
    if not image_paths: return
        
    faces, ids = [], []
    for image_path in image_paths:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        student_id = int(os.path.split(image_path)[-1].split(".")[1])
        faces.append(img)
        ids.append(student_id)

    if faces:
        recognizer.train(faces, np.array(ids))
        recognizer.write(TRAINER_FILE)

# NEW: Generator function for browser streaming
def gen_register_face(student_id, app_context):
    recognizer = None
    if os.path.exists(TRAINER_FILE):
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(TRAINER_FILE)

    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        cam = cv2.VideoCapture(0)

    count = 0
    try:
        while True:
            ret, frame = cam.read()
            if not ret: break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

            for (x, y, w, h) in faces:
                is_known = False
                
                # FEATURE: Ignore already registered faces
                if recognizer:
                    id_, dist = recognizer.predict(gray[y:y+h, x:x+w])
                    if dist < 75:
                        is_known = True
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                        cv2.putText(frame, "Known Face Ignored", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
                if not is_known:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    count += 1
                    file_name = f"{FACES_DIR}/User.{student_id}.{count}.jpg"
                    cv2.imwrite(file_name, gray[y:y+h, x:x+w])

            cv2.putText(frame, f"Collected: {count}/50", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Encode frame for HTTP stream
            ret, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            if count >= 50:
                break
    finally:
        cam.release()
        if count >= 50:
            train_model()
            with app_context.app_context():
                student = Student.query.get(student_id)
                if student:
                    student.face_registered = True
                    db.session.commit()

# NEW: Generator function for browser streaming
def gen_attendance(session_id, app_context, distance_threshold=75):
    if not os.path.exists(TRAINER_FILE):
        return # Cannot run without trained model

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(TRAINER_FILE)

    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        cam = cv2.VideoCapture(0)

    marked_present = set()

    try:
        while True:
            ret, frame = cam.read()
            if not ret: break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(100, 100))

            with app_context.app_context():
                session = AttendanceSession.query.get(session_id)
                if not session: break

                for (x, y, w, h) in faces:
                    student_id, distance = recognizer.predict(gray[y:y+h, x:x+w])
                    
                    if distance < distance_threshold:
                        student = Student.query.get(student_id)
                        
                        # FEATURE: Filter by Class. Reject if face belongs to wrong class.
                        if student and student.class_name == session.class_name:
                            label = f"{student.roll_no} (Match)"
                            color = (0, 255, 0)

                            if student_id not in marked_present:
                                marked_present.add(student_id)
                                record = AttendanceRecord(session_id=session_id, student_id=student_id, status="present")
                                db.session.add(record)
                                db.session.commit()
                        elif student:
                            label = f"Wrong Class ({student.class_name})"
                            color = (0, 255, 255) # Yellow for wrong class
                        else:
                            label = "Unknown Data"
                            color = (0, 0, 255)
                    else:
                        label = "Unknown"
                        color = (0, 0, 255)

                    cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                    cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # Encode frame for HTTP stream
            ret, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    finally:
        cam.release()