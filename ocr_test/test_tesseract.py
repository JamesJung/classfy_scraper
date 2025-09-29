#!/usr/bin/env python3

import time
import os
from pathlib import Path

def test_tesseract_ocr():
    try:
        import pytesseract
        from PIL import Image

        image_path = Path(__file__).parent / "test_image.jpg"

        if not image_path.exists():
            print(f"Error: Test image not found at {image_path}")
            return

        print("=" * 80)
        print("Tesseract OCR Performance Test")
        print("=" * 80)
        print(f"Test Image: {image_path}")
        print("-" * 80)

        print("\n[1/2] Loading image...")
        load_start = time.time()
        image = Image.open(image_path)
        load_time = time.time() - load_start
        print(f"Image loading time: {load_time:.2f} seconds")
        print(f"Image size: {image.size}")
        print(f"Image mode: {image.mode}")

        print("\n[2/2] Performing OCR with Tesseract...")
        ocr_start = time.time()
        try:
            text = pytesseract.image_to_string(image, lang='kor+eng')
        except Exception as e:
            print(f"Failed with 'kor+eng', trying 'eng' only: {e}")
            text = pytesseract.image_to_string(image, lang='eng')
        ocr_time = time.time() - ocr_start
        print(f"OCR processing time: {ocr_time:.2f} seconds")

        print("\n" + "=" * 80)
        print("Extracted Text:")
        print("=" * 80)
        print(text)

        text_lines = [line for line in text.split('\n') if line.strip()]

        print("\n" + "=" * 80)
        print("Performance Summary:")
        print("=" * 80)
        print(f"Image loading time:    {load_time:.2f}s")
        print(f"OCR processing time:   {ocr_time:.2f}s")
        print(f"Total time:            {load_time + ocr_time:.2f}s")
        print(f"Characters extracted:  {len(text)}")
        print(f"Lines extracted:       {len(text_lines)}")
        print("=" * 80)

        output_file = Path(__file__).parent / "tesseract_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\nOutput saved to: {output_file}")

        print("\n[Additional] Getting detailed OCR data...")
        data_start = time.time()
        try:
            data = pytesseract.image_to_data(image, lang='kor+eng', output_type=pytesseract.Output.DICT)
        except:
            data = pytesseract.image_to_data(image, lang='eng', output_type=pytesseract.Output.DICT)
        data_time = time.time() - data_start
        print(f"Data extraction time: {data_time:.2f} seconds")
        print(f"Total words detected: {len([w for w in data['text'] if w.strip()])}")

        return {
            "load_time": load_time,
            "ocr_time": ocr_time,
            "total_time": load_time + ocr_time,
            "text_length": len(text),
            "lines_count": len(text_lines)
        }

    except ImportError as e:
        print(f"Error: pytesseract or PIL is not installed. Please install them with:")
        print(f"  pip install pytesseract pillow")
        print(f"  Also ensure tesseract-ocr is installed on your system")
        print(f"\nDetailed error: {e}")
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tesseract_ocr()