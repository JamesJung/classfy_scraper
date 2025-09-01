import sys
from tarfile import data_filter
import traceback
import argparse
from pathlib import Path

from src.config.logConfig import setup_logging
from src.core.classificationProcessor import ClassificationProcessor

logger = setup_logging(__name__)
logger.debug("분류 전용 처리 시스템 시작")


def process_files_classification_only(args):
    """
    분류 전용 처리 시스템 (SUBVENTION_MASTER 자동 저장 방지)
    - 모든 파일 분류 → ANNOUNCEMENT_CLASSIFICATION만 저장
    - PRV 사이트 시도/시군구 구조 지원
    - webapp에서 수동 선별하여 개별 LLM 처리 진행
    """
    try:
        logger.info("🚀 분류 전용 처리 시스템 시작 (SUBVENTION_MASTER 자동 저장 방지)")
        logger.info("📋 처리 내용: 모든 공고 분류 → ANNOUNCEMENT_CLASSIFICATION만 저장")
        logger.info("🚫 SUBVENTION_MASTER 자동 저장 방지")
        logger.info("👤 webapp에서 수동 선별 후 개별 LLM 처리")

        from src.config.config import ConfigManager

        config = ConfigManager().get_config()
        root_dir = Path(config["directories"]["root_dir"])
        inpur_dir = Path(config["directories"]["input_dir"])
        


        #data_origin_path = root_dir / "data.origin"
        data_origin_path = inpur_dir

        if not data_origin_path.exists():
            logger.error(f"❌ data.origin 디렉토리가 존재하지 않음: {data_origin_path}")
            sys.exit(1)

        # 분류 전용 처리기 초기화
        processor = ClassificationProcessor()

        sites_to_process = []
        if hasattr(args, 'site_code') and args.site_code:
            site_path = data_origin_path / args.site_code
            if site_path.is_dir():
                sites_to_process.append(site_path)
            else:
                logger.warning(f"⚠️ 지정된 사이트가 존재하지 않습니다: {args.site_code}")
                return
        else:
            sites_to_process = [
                d for d in data_origin_path.iterdir() if d.is_dir()
            ]

        total_folders = 0
        processed_folders = 0
        excluded_folders = 0
        error_folders = 0

        for site_path in sites_to_process:
            site_code = site_path.name
            logger.info(f"📁 사이트 처리 중: {site_code}")

            # bizInfo 사이트 특별 처리 (JSON-폴더 매핑)
            if site_code.lower() == "bizinfo":
                logger.info(f"📁 bizInfo 사이트 JSON 기반 분류 처리: {site_code}")

                # JSON 파일들 찾기 (상위 디렉토리)
                json_files = list(site_path.glob("PBLN_*.json"))

                for json_file in json_files:
                    folder_name = json_file.stem  # PBLN_000000000112406
                    folder_path = site_path / folder_name

                    # 대응하는 폴더가 존재하는지 확인
                    if folder_path.exists() and folder_path.is_dir():
                        total_folders += 1

                        logger.info(f"📄 bizInfo 처리: {folder_name}")

                        # ClassificationProcessor로 JSON 직접 분류
                        result = processor.process_announcement_folder(folder_path, site_code)

                        if result:
                            if result.get("excluded"):
                                excluded_folders += 1
                                logger.info(f"⏭️  제외: {folder_name}")
                            else:
                                processed_folders += 1
                                classification_type = result.get('classification_type', 'UNKNOWN')
                                confidence = result.get('confidence_score', 0)
                                logger.info(f"✅ bizInfo JSON 분류: {folder_name} → {classification_type} ({confidence}%)")
                        else:
                            error_folders += 1
                            logger.error(f"❌ bizInfo 분류 실패: {folder_name}")

                        if hasattr(args, 'limit') and args.limit and total_folders >= args.limit:
                            break
                    else:
                        logger.warning(f"⚠️  bizInfo 폴더 없음: {folder_name}")
            # PRV 사이트는 특별 처리 (시도/시군구 구조)
            elif site_code.lower() == "prv":
                try:
                    from src.utils.folderUtil import get_prv_announcement_folders
                    prv_folders = get_prv_announcement_folders(site_path)

                    for announcement_dir, sido_name, sigungu_name, announcement_name in prv_folders:
                        total_folders += 1

                        # 분류 처리 실행 (ANNOUNCEMENT_CLASSIFICATION 저장만)
                        result = processor.process_announcement_folder(announcement_dir, site_code)

                        if result:
                            if result.get("excluded"):
                                excluded_folders += 1
                                logger.info(f"⏭️  제외: {announcement_name} ({sido_name}/{sigungu_name})")
                            else:
                                processed_folders += 1
                                logger.info(f"✅ 분류: {announcement_name} → {result.get('classification_type', 'UNKNOWN')}")
                        else:
                            error_folders += 1

                        if hasattr(args, 'limit') and args.limit and total_folders >= args.limit:
                            break

                except ImportError:
                    logger.warning(f"PRV 전용 처리 모듈을 찾을 수 없음, 일반 처리로 진행: {site_code}")
                    # 일반 처리로 fallback
                    folders = [f for f in site_path.iterdir() if f.is_dir()]
                    for folder_path in folders:
                        if (folder_path.name.startswith("processed_") or
                            folder_path.name.startswith("backup_") or
                            folder_path.name.startswith("temp_")):
                            continue

                        total_folders += 1
                        result = processor.process_announcement_folder(folder_path, site_code)

                        if result:
                            if result.get("excluded"):
                                excluded_folders += 1
                            else:
                                processed_folders += 1
                        else:
                            error_folders += 1

                        if hasattr(args, 'limit') and args.limit and total_folders >= args.limit:
                            break
            else:
                # 일반 사이트 처리
                folders = [f for f in site_path.iterdir() if f.is_dir()]

                for folder_path in folders:
                    # 메타데이터 폴더 제외
                    if (folder_path.name.startswith("processed_") or
                        folder_path.name.startswith("backup_") or
                        folder_path.name.startswith("temp_")):
                        continue

                    total_folders += 1

                    # 분류 처리 실행 (ANNOUNCEMENT_CLASSIFICATION 저장만)
                    result = processor.process_announcement_folder(folder_path, site_code)

                    if result:
                        if result.get("excluded"):
                            excluded_folders += 1
                            logger.info(f"⏭️  제외: {folder_path.name}")
                        else:
                            processed_folders += 1
                            logger.info(f"✅ 분류: {folder_path.name} → {result.get('classification_type', 'UNKNOWN')}")
                    else:
                        error_folders += 1

                    if hasattr(args, 'limit') and args.limit and total_folders >= args.limit:
                        break

                if hasattr(args, 'limit') and args.limit and total_folders >= args.limit:
                    break

        # 처리 완료 보고
        logger.info("🎉 분류 전용 처리 완료!")
        logger.info(f"📊 처리 결과:")
        logger.info(f"  ├── 총 폴더: {total_folders}개")
        logger.info(f"  ├── 분류 성공: {processed_folders}개")
        logger.info(f"  ├── 제외됨: {excluded_folders}개")
        logger.info(f"  └── 처리 오류: {error_folders}개")
        logger.info("🚫 SUBVENTION_MASTER 자동 저장 방지됨")
        logger.info("👤 webapp에서 수동 선별하여 개별 처리하세요")

        return {
            "classification_only": True,
            "total_folders": total_folders,
            "processed_folders": processed_folders,
            "excluded_folders": excluded_folders,
            "error_folders": error_folders,
            "subvention_master_saved": 0,  # 자동 저장 방지
            "manual_processing_required": True
        }

    except Exception as e:
        logger.error(f"분류 처리 중 오류 발생: {e}")
        traceback.print_exc()
        return {"classification_only": True, "processed_count": 0, "classification_errors": 1, "error": str(e)}


def main():
    """
    메인 함수 - 분류 전용 처리 시스템 (SUBVENTION_MASTER 자동 저장 방지)
    """
    parser = argparse.ArgumentParser(description="분류 전용 공고 처리 시스템")
    parser.add_argument("--site-code", type=str, help="특정 사이트만 처리")
    parser.add_argument("--limit", type=int, help="처리할 폴더 수 제한")
    parser.add_argument("--verbose", action="store_true", help="상세 로그 출력")

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # 분류 전용 처리 (SUBVENTION_MASTER 자동 저장 방지)
        logger.info("🏷️ 분류 전용 모드 (SUBVENTION_MASTER 자동 저장 방지)")
        result = process_files_classification_only(args)

        if result.get("classification_only"):
            logger.info("🎉 분류 전용 처리 성공!")
            logger.info(f"  ├── 총 폴더: {result.get('total_folders', 0)}개")
            logger.info(f"  ├── 분류 성공: {result.get('processed_folders', 0)}개")
            logger.info(f"  ├── 제외됨: {result.get('excluded_folders', 0)}개")
            logger.info(f"  └── 오류: {result.get('error_folders', 0)}개")

    except KeyboardInterrupt:
        logger.info("⚠️ 사용자에 의해 중단됨")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 실행 중 오류: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
