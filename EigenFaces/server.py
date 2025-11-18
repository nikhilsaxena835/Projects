import cv2
import numpy as np
import socket
import pickle
import threading
from ultralytics import YOLO

###################################### VARIABLES ######################################

top_k_eigenfaces = 700  

model = YOLO("./yolov8n-face-lindevs.pt")  # Face detection model

eigenfaces = np.load("./eigen_faces_f.npy").astype(np.float32)
eigenfaces = eigenfaces[:, :top_k_eigenfaces]

mean_face = np.load("./mean_faces_f.npy")

if mean_face.ndim > 1:
    mean_face = mean_face.flatten()  # Ensure it's a 1D vector

# Network Config
IP = "10.1.37.194"  # Server IP
FRIEND_IP = "10.1.37.175"
PORT = 5142 

YOUR_NAME = "Nikhil"
FRIEND_NAME = "Friend"

########################################################################################

BUFFER_SIZE = 65536

# Initialize socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((IP, PORT))
server_socket.setblocking(False)  # Non-blocking mode
print(f"Server listening on {IP}:{PORT}")

# Video Capture
cap = cv2.VideoCapture(0)

# Global variables for received data
received_compressed_face = None
received_addr = None

def receive_data():
    global received_compressed_face, received_addr
    while True:
        try:
            data, addr = server_socket.recvfrom(BUFFER_SIZE)
            received_compressed_face = pickle.loads(data)
            received_addr = addr
        except BlockingIOError:
            continue

# Start receiver thread
recv_thread = threading.Thread(target=receive_data, daemon=True)
recv_thread.start()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Convert to grayscale
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    results = model(frame)  # Run YOLO on original frame
    face_detected = False
    face_resized = np.zeros((120, 120), dtype=np.uint8)
    sender_reconstruction_cost = None 
    
    for result in results:
        for box in result.boxes:
            face_detected = True
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            face = gray_frame[y1:y2, x1:x2] 
            if face.size == 0:
                continue
            
            face_resized = cv2.resize(face, (120, 120))
            face_flatten = face_resized.flatten().astype(np.float32)
            face_normalized = face_flatten - mean_face
            
            # PCA Compression: Project onto eigenfaces
            compressed_face = eigenfaces.T @ face_normalized
            
            # Sender-side PCA Reconstruction
            sender_reconstructed = eigenfaces @ compressed_face + mean_face
            sender_reconstructed_clipped = np.clip(sender_reconstructed.reshape(120, 120), 0, 255).astype(np.uint8)
            sender_reconstruction_cost = np.mean((face_resized.astype(np.float32) - sender_reconstructed_clipped.astype(np.float32))**2)
            
            # Send compressed face to friend
            face_data = pickle.dumps(compressed_face)
            server_socket.sendto(face_data, (FRIEND_IP, PORT))
            break  # Process only the first detected face
    
    # Receiver-side reconstruction (for display only)
    if received_compressed_face is not None:
        receiver_reconstructed = eigenfaces @ received_compressed_face + mean_face
        receiver_reconstructed_clipped = np.clip(receiver_reconstructed.reshape(120, 120), 0, 255).astype(np.uint8)
    else:
        receiver_reconstructed_clipped = np.zeros((120, 120), dtype=np.uint8)

    # Calculate compression ratio
    # Original face size in bytes (120x120 grayscale, each pixel 1 byte)
    original_face_size = 120 * 120  
    compressed_size = top_k_eigenfaces * 4  # Each PCA coefficient as float32 (4 bytes)
    compression_ratio = (1 - (compressed_size / original_face_size)) * 100

    # Display Both Faces
    display_frame = np.zeros((500, 800, 3), dtype=np.uint8)  # Black background
    original_display = cv2.resize(face_resized, (200, 200))  # Sender's original face
    reconstructed_display = cv2.resize(receiver_reconstructed_clipped, (200, 200))  # Receiver's reconstructed face

    # Convert grayscale images to 3-channel for display
    original_display = cv2.cvtColor(original_display, cv2.COLOR_GRAY2BGR)
    reconstructed_display = cv2.cvtColor(reconstructed_display, cv2.COLOR_GRAY2BGR)

    # Add white border to images
    border_thickness = 5
    original_display = cv2.copyMakeBorder(original_display, border_thickness, border_thickness, border_thickness, border_thickness, 
                                          cv2.BORDER_CONSTANT, value=(255, 255, 255))
    reconstructed_display = cv2.copyMakeBorder(reconstructed_display, border_thickness, border_thickness, border_thickness, border_thickness, 
                                               cv2.BORDER_CONSTANT, value=(255, 255, 255))

    # Set positions for display
    sender_pos = (95, 145)
    receiver_pos = (495, 145)
    display_frame[sender_pos[1]:sender_pos[1]+210, sender_pos[0]:sender_pos[0]+210] = original_display
    display_frame[receiver_pos[1]:receiver_pos[1]+210, receiver_pos[0]:receiver_pos[0]+210] = reconstructed_display
    
    # Add labels above boxes
    cv2.putText(display_frame, YOUR_NAME, (sender_pos[0] + 20, sender_pos[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(display_frame, FRIEND_NAME, (receiver_pos[0] + 20, receiver_pos[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Add sender reconstruction cost below the sender image
    if sender_reconstruction_cost is not None:
        cv2.putText(display_frame, f"Cost: {sender_reconstruction_cost:.2f}", 
                    (sender_pos[0] + 10, sender_pos[1] + 230), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Add compression ratio below both images (centered)
    cv2.putText(display_frame, f"Compression: {compression_ratio:.2f}%", 
                (300, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Show message if no face detected
    if not face_detected:
        cv2.putText(display_frame, "No Face Detected", (300, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    
    cv2.imshow("Friend Video Call", display_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):   
        break

cap.release()
cv2.destroyAllWindows()
server_socket.close()
