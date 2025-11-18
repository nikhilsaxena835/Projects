import cv2
import numpy as np
from ultralytics import YOLO

###################################### VARIABLES ######################################

top_k_eigenfaces = 1000  # Number of top eigenfaces to use for compression

# YOLOv8 face detection model
model = YOLO("./yolov8n-face-lindevs.pt")

# Load precomputed eigenfaces and mean face in grayscale
eigenfaces = np.load("./eigen_faces.npy").astype(np.float32)  # Eigenfaces matrix
eigenfaces = eigenfaces[:, :top_k_eigenfaces]  # Use only top k eigenfaces
mean_face = np.load("./mean_faces.npy")  # Mean face vector

########################################################################################

# Initialize video capture
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Convert frame to grayscale
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Create a blank display background (colored background)
    display_frame = np.full((500, 800, 3), (30, 30, 30), dtype=np.uint8)  # Dark gray background
    center_x = display_frame.shape[1] // 2
    center_y = display_frame.shape[0] // 2
    box_size = 200  # Face box size
    border_thickness = 10  # Thickness of the colored frame
    frame_color = (255, 0, 0)  # Blue frame (changeable)

    # Run YOLO model on the frame
    results = model(frame)

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])  # Convert tensor to int coordinates
            face = gray_frame[y1:y2, x1:x2]
            if face.size == 0:
                continue
            
            # Get original face size before resizing
            original_h, original_w = face.shape[:2]
            original_face_size = original_h * original_w  # Since it's grayscale

            # Resize face to match PCA eigenface dimensions
            face_resized = cv2.resize(face, (120, 120))

            # Flatten face to 1D vector
            face_vector = face_resized.flatten()

            # Subtract mean face for normalization
            face_normalized = face_vector - mean_face

            # PCA Compression: Project onto eigenfaces
            compressed_representation = eigenfaces.T @ face_normalized

            # PCA Decompression: Reconstruct the face
            reconstructed_face = eigenfaces @ compressed_representation + mean_face

            # Reshape back to image dimensions and clip values
            reconstructed_face = np.clip(reconstructed_face.reshape(120, 120), 0, 255).astype(np.uint8)

            # Compute reconstruction error (MSE)
            reconstruction_cost = np.mean((face_resized - reconstructed_face) ** 2)

            # Compute compression percentage dynamically
            compressed_size = top_k_eigenfaces * 4  # Each PCA coefficient = 4 bytes (float32)
            if original_face_size > 0:
                compression_percentage = (1 - (compressed_size / original_face_size)) * 100
            else:
                compression_percentage = 0  # Avoid division by zero

            # Ensure compression percentage is within valid bounds (0 to 100)
            compression_percentage = max(0, min(compression_percentage, 100))

            # Resize for display
            original_display = cv2.resize(face_resized, (box_size, box_size))
            reconstructed_display = cv2.resize(reconstructed_face, (box_size, box_size))

            # Convert grayscale images to BGR for colored frame
            original_display = cv2.cvtColor(original_display, cv2.COLOR_GRAY2BGR)
            reconstructed_display = cv2.cvtColor(reconstructed_display, cv2.COLOR_GRAY2BGR)

            # Define positions for left (original) and right (reconstructed) boxes
            left_box = (center_x - box_size - 20, center_y - box_size // 2)
            right_box = (center_x + 20, center_y - box_size // 2)

            # Draw colored frame around original image
            display_frame[left_box[1] - border_thickness:left_box[1] + box_size + border_thickness,
                          left_box[0] - border_thickness:left_box[0] + box_size + border_thickness] = frame_color

            # Draw colored frame around reconstructed image
            display_frame[right_box[1] - border_thickness:right_box[1] + box_size + border_thickness,
                          right_box[0] - border_thickness:right_box[0] + box_size + border_thickness] = frame_color

            # Overlay the faces inside the frames
            display_frame[left_box[1]:left_box[1] + box_size, left_box[0]:left_box[0] + box_size] = original_display
            display_frame[right_box[1]:right_box[1] + box_size, right_box[0]:right_box[0] + box_size] = reconstructed_display

            # Draw white rectangle border for a clean frame effect
            cv2.rectangle(display_frame, 
                          (left_box[0] - border_thickness, left_box[1] - border_thickness), 
                          (left_box[0] + box_size + border_thickness, left_box[1] + box_size + border_thickness), 
                          (255, 255, 255), thickness=2)

            cv2.rectangle(display_frame, 
                          (right_box[0] - border_thickness, right_box[1] - border_thickness), 
                          (right_box[0] + box_size + border_thickness, right_box[1] + box_size + border_thickness), 
                          (255, 255, 255), thickness=2)

            # Draw labels
            cv2.putText(display_frame, "Original", (left_box[0], left_box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display_frame, f"Reconstructed (Loss: {reconstruction_cost:.2f})", 
                        (right_box[0], right_box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Positioning the compression percentage text at the center below both images
            text_position = (center_x - 100, center_y + box_size // 2 + 40)
            cv2.putText(display_frame, f"Compression: {compression_percentage:.2f}%", 
                        text_position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # Show the frame
    cv2.imshow("Face PCA Compression (Grayscale with Frame)", display_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
