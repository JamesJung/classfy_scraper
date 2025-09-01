#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일 경로 패턴 검증 및 SITE_CODE 일치성 확인 유틸리티

기능:
1. SUBVENTION_FILE_LIST 파일 경로와 SUBVENTION_MASTER의 SITE_CODE 일치성 검증
2. 파일 경로 패턴 분석 및 검증
3. 잘못된 파일 경로 감지 및 보고
4. 첨부파일 등록 시 실시간 검증
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


class ValidationResult(Enum):
    """검증 결과 상태"""
    VALID = "valid"
    INVALID_SITE_MISMATCH = "invalid_site_mismatch"
    INVALID_PATH_PATTERN = "invalid_path_pattern"
    INVALID_FOLDER_MISMATCH = "invalid_folder_mismatch"
    WARNING_SUSPICIOUS = "warning_suspicious"


@dataclass
class PathValidationResult:
    """경로 검증 결과"""
    result: ValidationResult
    message: str
    expected_site: Optional[str] = None
    actual_site: Optional[str] = None
    expected_folder: Optional[str] = None
    actual_folder: Optional[str] = None
    confidence_score: float = 1.0


class FilePathValidator:
    """파일 경로 패턴 검증기"""
    
    def __init__(self):
        self.logger = logger.getChild(self.__class__.__name__)
        
        # 사이트별 경로 패턴 정의
        self.site_path_patterns = {
            'bizinfo': {
                'pattern': r'^bizinfo/PBLN_\d+/',
                'description': 'bizinfo/PBLN_숫자/ 패턴',
                'folder_pattern': r'PBLN_\d+'
            },
            'gtp': {
                'pattern': r'^gtp/[\w\d가-힣\s\(\)\[\]_\-\.\「\」\<\>]+/',
                'description': 'gtp/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.\「\」\<\>]+'
            },
            'koita': {
                'pattern': r'^koita/[\w\d가-힣\s\(\)\[\]_\-\.]+/',
                'description': 'koita/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.]+'
            },
            'seoultp': {
                'pattern': r'^seoultp/[\w\d가-힣\s\(\)\[\]_\-\.]+/',
                'description': 'seoultp/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.]+'
            },
            'cceiChungbuk': {
                'pattern': r'^cceiChungbuk/[\w\d가-힣\s\(\)\[\]_\-\.]+/',
                'description': 'cceiChungbuk/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.]+'
            },
            'mcst': {
                'pattern': r'^mcst/[\w\d가-힣\s\(\)\[\]_\-\.]+/',
                'description': 'mcst/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.]+'
            },
            'pajucci': {
                'pattern': r'^pajucci/[\w\d가-힣\s\(\)\[\]_\-\.]+/',
                'description': 'pajucci/폴더명/ 패턴',
                'folder_pattern': r'[\w\d가-힣\s\(\)\[\]_\-\.]+'
            }
        }
    
    def extract_site_from_path(self, file_path: str) -> Optional[str]:
        """파일 경로에서 사이트 코드 추출"""
        try:
            if not file_path:
                return None
                
            # 경로 정규화 (백슬래시를 슬래시로 변환)
            normalized_path = file_path.replace('\\', '/')
                
            # data.origin/ 제거 (있는 경우)
            clean_path = normalized_path
            if 'data.origin/' in clean_path:
                parts = clean_path.split('data.origin/')
                if len(parts) > 1:
                    clean_path = parts[1]
            
            # 첫 번째 디렉토리가 사이트 코드
            path_parts = clean_path.split('/')
            if path_parts and path_parts[0]:
                return path_parts[0]  # 원본 대소문자 보존
                
        except Exception as e:
            self.logger.warning(f"경로에서 사이트 추출 실패: {file_path} - {e}")
            
        return None
    
    def extract_folder_from_path(self, file_path: str) -> Optional[str]:
        """파일 경로에서 폴더명 추출"""
        try:
            if not file_path:
                return None
                
            # 경로 정규화 (백슬래시를 슬래시로 변환)
            normalized_path = file_path.replace('\\', '/')
                
            # data.origin/ 제거 (있는 경우)
            clean_path = normalized_path
            if 'data.origin/' in clean_path:
                parts = clean_path.split('data.origin/')
                if len(parts) > 1:
                    clean_path = parts[1]
            
            # site/folder/ 패턴에서 folder 추출
            path_parts = clean_path.split('/')
            if len(path_parts) >= 2 and path_parts[1]:
                return path_parts[1]
                
        except Exception as e:
            self.logger.warning(f"경로에서 폴더 추출 실패: {file_path} - {e}")
            
        return None
    
    def validate_path_pattern(self, file_path: str, expected_site: str) -> PathValidationResult:
        """파일 경로 패턴 검증"""
        try:
            if not file_path or not expected_site:
                return PathValidationResult(
                    result=ValidationResult.INVALID_PATH_PATTERN,
                    message="파일 경로 또는 사이트 코드가 비어있음"
                )
            
            expected_site_lower = expected_site.lower()
            
            # 사이트별 패턴 확인 (대소문자 무관)
            matching_site_key = None
            for site_key in self.site_path_patterns.keys():
                if site_key.lower() == expected_site_lower:
                    matching_site_key = site_key
                    break
            
            if not matching_site_key:
                return PathValidationResult(
                    result=ValidationResult.WARNING_SUSPICIOUS,
                    message=f"알 수 없는 사이트 코드: {expected_site}",
                    confidence_score=0.5
                )
            
            pattern_info = self.site_path_patterns[matching_site_key]
            pattern = pattern_info['pattern']
            
            # 경로 정규화 및 data.origin/ 제거 후 패턴 매칭
            normalized_path = file_path.replace('\\', '/')
            clean_path = normalized_path
            if 'data.origin/' in clean_path:
                parts = clean_path.split('data.origin/')
                if len(parts) > 1:
                    clean_path = parts[1]
            
            if re.match(pattern, clean_path, re.IGNORECASE):
                return PathValidationResult(
                    result=ValidationResult.VALID,
                    message="경로 패턴이 올바름",
                    confidence_score=1.0
                )
            else:
                return PathValidationResult(
                    result=ValidationResult.INVALID_PATH_PATTERN,
                    message=f"경로 패턴 불일치. 기대: {pattern_info['description']}, 실제: {clean_path}",
                    confidence_score=0.0
                )
                
        except Exception as e:
            self.logger.error(f"경로 패턴 검증 실패: {file_path} - {e}")
            return PathValidationResult(
                result=ValidationResult.INVALID_PATH_PATTERN,
                message=f"검증 중 오류 발생: {str(e)}",
                confidence_score=0.0
            )
    
    def validate_site_consistency(self, file_path: str, expected_site: str) -> PathValidationResult:
        """SITE_CODE와 파일 경로의 사이트 일치성 검증"""
        try:
            actual_site = self.extract_site_from_path(file_path)
            
            if not actual_site:
                return PathValidationResult(
                    result=ValidationResult.INVALID_SITE_MISMATCH,
                    message="파일 경로에서 사이트를 추출할 수 없음",
                    expected_site=expected_site,
                    actual_site=None
                )
            
            if not expected_site:
                return PathValidationResult(
                    result=ValidationResult.INVALID_SITE_MISMATCH,
                    message="기대되는 사이트 코드가 비어있음",
                    expected_site=None,
                    actual_site=actual_site
                )
            
            # 대소문자 무관 비교
            if actual_site.lower() == expected_site.lower():
                return PathValidationResult(
                    result=ValidationResult.VALID,
                    message="사이트 코드 일치",
                    expected_site=expected_site,
                    actual_site=actual_site,
                    confidence_score=1.0
                )
            else:
                return PathValidationResult(
                    result=ValidationResult.INVALID_SITE_MISMATCH,
                    message=f"사이트 코드 불일치",
                    expected_site=expected_site,
                    actual_site=actual_site,
                    confidence_score=0.0
                )
                
        except Exception as e:
            self.logger.error(f"사이트 일치성 검증 실패: {file_path} vs {expected_site} - {e}")
            return PathValidationResult(
                result=ValidationResult.INVALID_SITE_MISMATCH,
                message=f"검증 중 오류 발생: {str(e)}",
                expected_site=expected_site,
                actual_site=None,
                confidence_score=0.0
            )
    
    def validate_folder_consistency(self, file_path: str, expected_folder: str) -> PathValidationResult:
        """폴더명 일치성 검증"""
        try:
            actual_folder = self.extract_folder_from_path(file_path)
            
            if not actual_folder:
                return PathValidationResult(
                    result=ValidationResult.INVALID_FOLDER_MISMATCH,
                    message="파일 경로에서 폴더명을 추출할 수 없음",
                    expected_folder=expected_folder,
                    actual_folder=None
                )
            
            if not expected_folder:
                return PathValidationResult(
                    result=ValidationResult.WARNING_SUSPICIOUS,
                    message="기대되는 폴더명이 비어있음",
                    expected_folder=None,
                    actual_folder=actual_folder,
                    confidence_score=0.5
                )
            
            # 폴더명 유사도 검사 (정확히 일치하거나 포함관계)
            if actual_folder == expected_folder:
                confidence = 1.0
            elif expected_folder in actual_folder or actual_folder in expected_folder:
                confidence = 0.8
            else:
                confidence = 0.0
            
            if confidence >= 0.8:
                return PathValidationResult(
                    result=ValidationResult.VALID,
                    message="폴더명 일치" if confidence == 1.0 else "폴더명 유사",
                    expected_folder=expected_folder,
                    actual_folder=actual_folder,
                    confidence_score=confidence
                )
            else:
                return PathValidationResult(
                    result=ValidationResult.INVALID_FOLDER_MISMATCH,
                    message="폴더명 불일치",
                    expected_folder=expected_folder,
                    actual_folder=actual_folder,
                    confidence_score=confidence
                )
                
        except Exception as e:
            self.logger.error(f"폴더 일치성 검증 실패: {file_path} vs {expected_folder} - {e}")
            return PathValidationResult(
                result=ValidationResult.INVALID_FOLDER_MISMATCH,
                message=f"검증 중 오류 발생: {str(e)}",
                expected_folder=expected_folder,
                actual_folder=None,
                confidence_score=0.0
            )
    
    def comprehensive_validate(self, file_path: str, expected_site: str, 
                             expected_folder: Optional[str] = None) -> List[PathValidationResult]:
        """종합적인 파일 경로 검증"""
        results = []
        
        # 1. 사이트 코드 일치성 검증
        site_result = self.validate_site_consistency(file_path, expected_site)
        results.append(site_result)
        
        # 2. 경로 패턴 검증
        pattern_result = self.validate_path_pattern(file_path, expected_site)
        results.append(pattern_result)
        
        # 3. 폴더명 일치성 검증 (제공된 경우)
        if expected_folder:
            folder_result = self.validate_folder_consistency(file_path, expected_folder)
            results.append(folder_result)
        
        return results
    
    def is_valid_file_path(self, file_path: str, expected_site: str, 
                          expected_folder: Optional[str] = None) -> Tuple[bool, List[str]]:
        """파일 경로 유효성 간단 검사 (True/False + 메시지들)"""
        results = self.comprehensive_validate(file_path, expected_site, expected_folder)
        
        is_valid = True
        messages = []
        
        for result in results:
            if result.result in [ValidationResult.INVALID_SITE_MISMATCH, 
                               ValidationResult.INVALID_PATH_PATTERN, 
                               ValidationResult.INVALID_FOLDER_MISMATCH]:
                is_valid = False
                messages.append(f"❌ {result.message}")
            elif result.result == ValidationResult.WARNING_SUSPICIOUS:
                messages.append(f"⚠️ {result.message}")
            else:
                messages.append(f"✅ {result.message}")
        
        return is_valid, messages


# 전역 인스턴스
_path_validator = None

def get_file_path_validator() -> FilePathValidator:
    """파일 경로 검증기 전역 인스턴스 반환"""
    global _path_validator
    if _path_validator is None:
        _path_validator = FilePathValidator()
    return _path_validator


def validate_file_path(file_path: str, site_code: str, 
                      folder_name: Optional[str] = None) -> Tuple[bool, List[str]]:
    """파일 경로 검증 헬퍼 함수"""
    validator = get_file_path_validator()
    return validator.is_valid_file_path(file_path, site_code, folder_name)