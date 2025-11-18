import cv2
import numpy as np
import os
import random
import glob

def random_rotation(image, angle_range=(-15, 15)):
    """Rotate the image by a random angle within angle_range."""
    angle = random.uniform(*angle_range)
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1)
    rotated = cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return rotated

def random_flip(image):
    """Randomly flip the image horizontally."""
    if random.random() < 0.5:
        return cv2.flip(image, 1)  # horizontal flip
    return image

def random_brightness_contrast(image, brightness_range=(-50, 50), contrast_range=(0.8, 1.2)):
    """Randomly adjust brightness and contrast."""
    brightness = random.randint(*brightness_range)
    contrast = random.uniform(*contrast_range)
    new_img = cv2.convertScaleAbs(image, alpha=contrast, beta=brightness)
    return new_img

def random_noise(image, noise_level=10):
    """Add random Gaussian noise to the image."""
    row, col, ch = image.shape
    mean = 0
    sigma = noise_level
    gauss = np.random.normal(mean, sigma, (row, col, ch)).reshape(row, col, ch)
    noisy = image + gauss
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)
    return noisy

def random_crop_zoom(image, scale_range=(0.9, 1.1)):
    """Randomly zoom in/out and crop or pad the image to original size."""
    h, w = image.shape[:2]
    scale = random.uniform(*scale_range)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h))
    
    if scale > 1:
        # Crop the center of the zoomed image
        x = (new_w - w) // 2
        y = (new_h - h) // 2
        cropped = resized[y:y+h, x:x+w]
    else:
        # Pad image to reach original size
        pad_w = (w - new_w) // 2
        pad_h = (h - new_h) // 2
        cropped = cv2.copyMakeBorder(resized, pad_h, h - new_h - pad_h, pad_w, w - new_w - pad_w, cv2.BORDER_REPLICATE)
    return cropped

def augment_image(image):
    """Apply a series of random augmentations to the input image."""
    aug_image = image.copy()
    aug_image = random_rotation(aug_image)
    aug_image = random_flip(aug_image)
    aug_image = random_brightness_contrast(aug_image)
    # Optionally add noise with 50% probability
    if random.random() < 0.5:
        aug_image = random_noise(aug_image)
    aug_image = random_crop_zoom(aug_image)
    return aug_image

def generate_dataset(input_folder, output_dir, total_images=1000):
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Get list of all image files in the folder
    image_paths = glob.glob(os.path.join(input_folder, "*.*"))
    if not image_paths:
        raise ValueError(f"No images found in folder: {input_folder}")

    print(f"Found {len(image_paths)} images in '{input_folder}'.")

    count = 0
    # Loop until we have generated the desired number of images
    while count < total_images:
        for path in image_paths:
            if count >= total_images:
                break
            image = cv2.imread(path)
            if image is None:
                print(f"Warning: Could not load image: {path}")
                continue
            aug_img = augment_image(image)
            output_path = os.path.join(output_dir, f"augmented_{count:04d}.jpg")
            cv2.imwrite(output_path, aug_img)
            count += 1
            if count % 100 == 0:
                print(f"{count} images generated...")
    print("Dataset generation complete.")

if __name__ == "__main__":
    input_folder = "face_dataset/person"            # Folder containing original face images
    output_dir = "augmented_dataset"  # Output folder for augmented images
    total_images = 1000               # Total number of augmented images to generate

    generate_dataset(input_folder, output_dir, total_images)