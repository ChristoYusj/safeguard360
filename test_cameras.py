"""
Test camera indices to find available cameras (including iVCam)
"""
import cv2
import time

print("Testing camera indices 0-5...\n")

for index in range(6):
    print(f"Index {index}: ", end="")
    
    # Try with DirectShow on Windows
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("FAILED to open")
        continue
    
    print("OPENED successfully")
    
    # Try to read a frame
    ret, frame = cap.read()
    if ret and frame is not None:
        h, w = frame.shape[:2]
        print(f"         Frame size: {w}x{h}")
        
        # Show the frame
        window_name = f"Camera {index} - Press any key"
        cv2.imshow(window_name, frame)
        cv2.waitKey(1500)  # Show for 1.5 seconds
        cv2.destroyWindow(window_name)
    else:
        print("         Could not read frame")
    
    cap.release()
    time.sleep(0.5)

print("\nDone testing cameras.")
cv2.destroyAllWindows()
