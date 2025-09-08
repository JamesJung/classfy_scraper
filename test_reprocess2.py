#!/usr/bin/env python3

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    print("1. 기본 import 시작...")
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    print("✅ 기본 import 완료")

    print("2. Ollama client import 시작...")
    from src.utils.ollamaClient import AnnouncementPrvAnalyzer, AnnouncementAnalyzer
    print("✅ Ollama client import 완료")

    print("3. Database manager import 시작...")
    from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager
    from src.models.announcementDatabase import AnnouncementDatabaseManager
    print("✅ Database manager import 완료")

    print("4. Logger 설정 시작...")
    logger = setup_logging(__name__)
    config = ConfigManager().get_config()
    print("✅ Logger 설정 완료")

    print("5. AnnouncementReprocessor 클래스 초기화 시작...")
    
    class TestReprocessor:
        def __init__(self):
            print("  - PRV DB Manager 초기화...")
            self.prv_db_manager = AnnouncementPrvDatabaseManager()
            print("  - SCRAP DB Manager 초기화...")  
            self.scrap_db_manager = AnnouncementDatabaseManager()
            print("  - PRV Analyzer 초기화...")
            self.prv_analyzer = AnnouncementPrvAnalyzer()
            print("  - SCRAP Analyzer 초기화...")
            self.scrap_analyzer = AnnouncementAnalyzer()
            print("  - 초기화 완료")
    
    print("6. 테스트 인스턴스 생성...")
    test_instance = TestReprocessor()
    print("✅ 모든 초기화 완료!")

except Exception as e:
    print(f"❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()