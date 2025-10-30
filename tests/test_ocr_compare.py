import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as main_mod
from thread_single import PaddleOCRModelManager

# Reuse mappings from main.py to keep fields in sync
KEYWORDS: Dict[str, List[str]] = getattr(main_mod, 'KEYWORDS')
ITEM_KEY_MAP: Dict[str, str] = getattr(main_mod, 'ITEM_KEY_MAP')


def find_pdf_json_pairs(data_dir: Path) -> List[Tuple[Path, Path]]:
    pairs = []
    for pdf_path in sorted(data_dir.glob('*.pdf')):
        json_path = pdf_path.with_suffix('.json')
        if json_path.exists():
            pairs.append((pdf_path, json_path))
    return pairs


def compute_main_accuracy(result: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    # Fields to compare: dynamic from KEYWORDS plus 'invoice_type'
    keys = list(KEYWORDS.keys()) + ['invoice_type']
    recognized = 0
    matched = 0
    total = len(keys)
    mismatches = []

    for k in keys:
        res_val = result.get(k)
        truth_val = truth.get(k)
        if res_val is not None and str(res_val).strip() != '':
            recognized += 1
        if truth_val is not None:
            # Only compare when truth exists; count match when strings equal after cleaning
            if (res_val is not None) and (str(res_val).strip() == str(truth_val).strip()):
                matched += 1
            else:
                mismatches.append({'field': k, 'result': res_val, 'truth': truth_val})
        else:
            # If truth doesn't provide the field, treat as mismatch context but don't penalize matched
            mismatches.append({'field': k, 'result': res_val, 'truth': None})

    recognition_rate = recognized / total if total else 0.0
    accuracy_rate = matched / total if total else 0.0
    return {
        'recognition_rate': recognition_rate,
        'accuracy_rate': accuracy_rate,
        'recognized': recognized,
        'matched': matched,
        'total': total,
        'mismatches': mismatches,
    }


def compute_items_accuracy(result_items: List[Dict[str, Any]], truth_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Compare on the set of mapped output keys (values of ITEM_KEY_MAP)
    item_keys = sorted(set(ITEM_KEY_MAP.values()))
    total_fields = 0
    recognized_fields = 0
    matched_fields = 0
    mismatches = []

    # Align by index; assumes truth and result lists correspond row-by-row
    max_len = max(len(result_items), len(truth_items))
    for idx in range(max_len):
        res_row = result_items[idx] if idx < len(result_items) else {}
        truth_row = truth_items[idx] if idx < len(truth_items) else {}
        for k in item_keys:
            total_fields += 1
            res_val = res_row.get(k)
            truth_val = truth_row.get(k)
            if res_val is not None and str(res_val).strip() != '':
                recognized_fields += 1
            if truth_val is not None:
                if (res_val is not None) and (str(res_val).strip() == str(truth_val).strip()):
                    matched_fields += 1
                else:
                    mismatches.append({'row': idx, 'field': k, 'result': res_val, 'truth': truth_val})
            else:
                mismatches.append({'row': idx, 'field': k, 'result': res_val, 'truth': None})

    recognition_rate = recognized_fields / total_fields if total_fields else 0.0
    accuracy_rate = matched_fields / total_fields if total_fields else 0.0
    return {
        'recognition_rate': recognition_rate,
        'accuracy_rate': accuracy_rate,
        'recognized': recognized_fields,
        'matched': matched_fields,
        'total': total_fields,
        'mismatches': mismatches,
    }


def run_case(pdf_path: Path, json_path: Path) -> Dict[str, Any]:
    with json_path.open('r', encoding='utf-8') as f:
        truth = json.load(f)

    model_manager = PaddleOCRModelManager()
    image_list = model_manager.read_pdf(pdf_path)

    # Use main.extract_invoice_info to structure OCR outputs
    result = main_mod.extract_invoice_info(image_list)
    result_main = result.get('main', {})
    result_items = result.get('items', [])

    truth_main = truth.get('main', {})
    truth_items = truth.get('items', [])

    main_stats = compute_main_accuracy(result_main, truth_main)
    items_stats = compute_items_accuracy(result_items, truth_items)

    # Weighted overall by total fields of each part
    total_weight = (main_stats['total'] + items_stats['total']) or 1
    overall_recognition = (
        (main_stats['recognition_rate'] * main_stats['total']) +
        (items_stats['recognition_rate'] * items_stats['total'])
    ) / total_weight
    overall_accuracy = (
        (main_stats['accuracy_rate'] * main_stats['total']) +
        (items_stats['accuracy_rate'] * items_stats['total'])
    ) / total_weight

    return {
        'pdf': str(pdf_path),
        'json': str(json_path),
        'main': main_stats,
        'items': items_stats,
        'overall_recognition': overall_recognition,
        'overall_accuracy': overall_accuracy,
    }


def run_all_tests(data_dir: Path = ROOT / 'data') -> None:
    pairs = find_pdf_json_pairs(data_dir)
    if not pairs:
        print(f'[WARN] No PDF/JSON pairs found in {data_dir}')
        return

    overall_rec_sum = 0.0
    overall_acc_sum = 0.0

    print(f'[INFO] Found {len(pairs)} case(s)')
    for pdf_path, json_path in pairs:
        stats = run_case(pdf_path, json_path)
        print('\n=== Case ===')
        print(f'PDF: {stats["pdf"]}')
        print(f'JSON: {stats["json"]}')
        print(f'Main: recognition={stats["main"]["recognition_rate"]:.3f}, accuracy={stats["main"]["accuracy_rate"]:.3f}, total={stats["main"]["total"]}')
        print(f'Items: recognition={stats["items"]["recognition_rate"]:.3f}, accuracy={stats["items"]["accuracy_rate"]:.3f}, total={stats["items"]["total"]}')
        print(f'Overall: recognition={stats["overall_recognition"]:.3f}, accuracy={stats["overall_accuracy"]:.3f}')

        # Show up to 10 mismatches for quick inspection
        mm_main = stats['main']['mismatches'][:10]
        mm_items = stats['items']['mismatches'][:10]
        if mm_main:
            print('[MISMATCH][MAIN] sample:')
            for mm in mm_main:
                print(f" - {mm['field']}: result='{mm['result']}' | truth='{mm['truth']}'")
        if mm_items:
            print('[MISMATCH][ITEMS] sample:')
            for mm in mm_items:
                print(f" - row {mm['row']} {mm['field']}: result='{mm['result']}' | truth='{mm['truth']}'")

        overall_rec_sum += stats['overall_recognition']
        overall_acc_sum += stats['overall_accuracy']

    n = len(pairs)
    print('\n=== Summary ===')
    print(f'Average overall recognition: {overall_rec_sum / n:.3f}')
    print(f'Average overall accuracy: {overall_acc_sum / n:.3f}')


if __name__ == '__main__':
    run_all_tests()