#!/usr/bin/env python3

import time
import os
from pathlib import Path

def test_paddleocr():
    try:
        from paddleocr import PaddleOCR

        image_path = Path(__file__).parent / "test_image.jpg"

        if not image_path.exists():
            print(f"Error: Test image not found at {image_path}")
            return

        print("=" * 80)
        print("PaddleOCR Performance Test")
        print("=" * 80)
        print(f"Test Image: {image_path}")
        print("-" * 80)

        print("\n[1/2] Initializing PaddleOCR (Korean + English)...")
        init_start = time.time()
        ocr = PaddleOCR(use_textline_orientation=True, lang='korean')
        init_time = time.time() - init_start
        print(f"PaddleOCR initialization time: {init_time:.2f} seconds")

        print("\n[2/2] Performing OCR...")
        ocr_start = time.time()
        result = ocr.predict(str(image_path))
        ocr_time = time.time() - ocr_start
        print(f"OCR processing time: {ocr_time:.2f} seconds")

        print("\n" + "=" * 80)
        print("Extracted Text with Confidence:")
        print("=" * 80)

        text_lines = []
        confidences = []

        if result and result[0]:
            for line in result[0]:
                if isinstance(line, (list, tuple)) and len(line) >= 2:
                    bbox = line[0]
                    if isinstance(line[1], (list, tuple)) and len(line[1]) >= 2:
                        text = line[1][0]
                        confidence = line[1][1]
                    elif isinstance(line[1], str):
                        text = line[1]
                        confidence = 1.0
                    else:
                        continue
                    print(f"[{confidence:.2f}] {text}")
                    text_lines.append(text)
                    confidences.append(confidence)

        full_text = "\n".join(text_lines)

        print("\n" + "=" * 80)
        print("Performance Summary:")
        print("=" * 80)
        print(f"Initialization time:   {init_time:.2f}s")
        print(f"OCR processing time:   {ocr_time:.2f}s")
        print(f"Total time:            {init_time + ocr_time:.2f}s")
        print(f"Characters extracted:  {len(full_text)}")
        print(f"Lines extracted:       {len(text_lines)}")
        if confidences:
            print(f"Average confidence:    {sum(confidences) / len(confidences):.2f}")
        print("=" * 80)

        output_file = Path(__file__).parent / "paddleocr_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\nOutput saved to: {output_file}")

        detailed_output_file = Path(__file__).parent / "paddleocr_detailed.txt"
        with open(detailed_output_file, "w", encoding="utf-8") as f:
            if result and result[0]:
                for line in result[0]:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        bbox = line[0]
                        if isinstance(line[1], (list, tuple)) and len(line[1]) >= 2:
                            text = line[1][0]
                            confidence = line[1][1]
                        elif isinstance(line[1], str):
                            text = line[1]
                            confidence = 1.0
                        else:
                            continue
                        f.write(f"Confidence: {confidence:.4f}\n")
                        f.write(f"BBox: {bbox}\n")
                        f.write(f"Text: {text}\n")
                        f.write("-" * 80 + "\n")
        print(f"Detailed output saved to: {detailed_output_file}")

        return {
            "init_time": init_time,
            "ocr_time": ocr_time,
            "total_time": init_time + ocr_time,
            "text_length": len(full_text),
            "lines_count": len(text_lines),
            "avg_confidence": sum(confidences) / len(confidences) if confidences else 0
        }

    except ImportError as e:
        print(f"Error: PaddleOCR is not installed. Please install it with:")
        print(f"  pip install paddleocr paddlepaddle")
        print(f"  For GPU support: pip install paddlepaddle-gpu")
        print(f"\nDetailed error: {e}")
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_paddleocr()