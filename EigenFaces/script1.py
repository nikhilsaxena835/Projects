import cv2
import os
import time

def capture_faces(dataset_path='dataset', person_name='subject', num_samples=50):
    os.makedirs(dataset_path, exist_ok=True)
    person_folder = os.path.join(dataset_path, person_name)
    os.makedirs(person_folder, exist_ok=True)
    
    face_cascade = cv2.CascadeClassifier(os.path.expanduser('~/.opencv/haarcascade_frontalface_default.xml'))

    cap = cv2.VideoCapture(0)
    
    count = 51
    while count < num_samples+50:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture image")
            break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
        
        for (x, y, w, h) in faces:
            face = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face, (200, 200))
            img_path = os.path.join(person_folder, f'{count}.jpg')
            cv2.imwrite(img_path, face_resized)
            count += 1
            print(f'Captured {count}/{num_samples}')
            time.sleep(0.5)  # Delay to allow different expressions and positions
        
        cv2.imshow('Capturing Faces', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print(f'Dataset for {person_name} saved in {person_folder}')

if __name__ == "__main__":
    capture_faces(dataset_path='face_dataset', person_name='person', num_samples=50)