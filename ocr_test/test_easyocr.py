#!/usr/bin/env python3

import time
import os
from pathlib import Path

def test_easyocr():
    try:
        import easyocr

        image_path = Path(__file__).parent / "test_image.jpg"

        if not image_path.exists():
            print(f"Error: Test image not found at {image_path}")
            return

        print("=" * 80)
        print("EasyOCR Performance Test")
        print("=" * 80)
        print(f"Test Image: {image_path}")
        print("-" * 80)

        print("\n[1/2] Initializing EasyOCR Reader (Korean + English)...")
        reader_start = time.time()
        reader = easyocr.Reader(['ko', 'en'], gpu=True)
        reader_time = time.time() - reader_start
        print(f"Reader initialization time: {reader_time:.2f} seconds")

        print("\n[2/2] Performing OCR...")
        ocr_start = time.time()
        results = reader.readtext(str(image_path))
        ocr_time = time.time() - ocr_start
        print(f"OCR processing time: {ocr_time:.2f} seconds")

        print("\n" + "=" * 80)
        print("Extracted Text with Confidence:")
        print("=" * 80)

        text_lines = []
        for bbox, text, confidence in results:
            print(f"[{confidence:.2f}] {text}")
            text_lines.append(text)

        full_text = "\n".join(text_lines)

        print("\n" + "=" * 80)
        print("Performance Summary:")
        print("=" * 80)
        print(f"Reader init time:      {reader_time:.2f}s")
        print(f"OCR processing time:   {ocr_time:.2f}s")
        print(f"Total time:            {reader_time + ocr_time:.2f}s")
        print(f"Characters extracted:  {len(full_text)}")
        print(f"Lines extracted:       {len(text_lines)}")
        print(f"Average confidence:    {sum(c for _, _, c in results) / len(results):.2f}")
        print("=" * 80)

        output_file = Path(__file__).parent / "easyocr_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\nOutput saved to: {output_file}")

        detailed_output_file = Path(__file__).parent / "easyocr_detailed.txt"
        with open(detailed_output_file, "w", encoding="utf-8") as f:
            for bbox, text, confidence in results:
                f.write(f"Confidence: {confidence:.4f}\n")
                f.write(f"BBox: {bbox}\n")
                f.write(f"Text: {text}\n")
                f.write("-" * 80 + "\n")
        print(f"Detailed output saved to: {detailed_output_file}")

        return {
            "reader_time": reader_time,
            "ocr_time": ocr_time,
            "total_time": reader_time + ocr_time,
            "text_length": len(full_text),
            "lines_count": len(text_lines),
            "avg_confidence": sum(c for _, _, c in results) / len(results) if results else 0
        }

    except ImportError as e:
        print(f"Error: EasyOCR is not installed. Please install it with:")
        print(f"  pip install easyocr")
        print(f"\nDetailed error: {e}")
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_easyocr()