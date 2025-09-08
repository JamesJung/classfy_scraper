#!/usr/bin/env python3
"""
Ollama 서버 리소스 모니터링 모듈

원격 서버의 CPU, GPU, 메모리, 네트워크 사용률을 실시간으로 모니터링합니다.
"""

import asyncio
import time
import json
import subprocess
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
import threading

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


@dataclass
class ResourceSnapshot:
    """리소스 사용량 스냅샷"""
    timestamp: float
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    memory_percent: float
    network_sent_mb: float
    network_recv_mb: float
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0
    gpu_utilization_percent: float = 0.0
    ollama_process_cpu: float = 0.0
    ollama_process_memory_mb: float = 0.0


@dataclass
class MonitoringSession:
    """모니터링 세션 데이터"""
    session_id: str
    start_time: float
    end_time: float
    duration: float
    snapshots: List[ResourceSnapshot]
    
    # 통계
    avg_cpu_percent: float = 0.0
    max_cpu_percent: float = 0.0
    avg_memory_percent: float = 0.0
    max_memory_percent: float = 0.0
    avg_gpu_utilization: float = 0.0
    max_gpu_utilization: float = 0.0
    avg_gpu_memory_percent: float = 0.0
    max_gpu_memory_percent: float = 0.0


class RemoteResourceMonitor:
    """원격 서버 리소스 모니터"""
    
    def __init__(self, 
                 server_host: str = "192.168.0.40",
                 ssh_user: str = "zium",
                 ssh_password: str = "zium1207!!",
                 monitoring_interval: float = 2.0):
        """
        Args:
            server_host: 모니터링할 서버 호스트
            ssh_user: SSH 사용자명
            ssh_password: SSH 비밀번호
            monitoring_interval: 모니터링 간격 (초)
        """
        self.server_host = server_host
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.monitoring_interval = monitoring_interval
        
        self.is_monitoring = False
        self.snapshots: List[ResourceSnapshot] = []
        self.monitor_thread: Optional[threading.Thread] = None
        
    def _execute_remote_command(self, command: str) -> Optional[str]:
        """SSH를 통해 원격 명령 실행"""
        try:
            # sshpass를 사용한 원격 명령 실행
            ssh_cmd = [
                "sshpass", "-p", self.ssh_password,
                "ssh", "-o", "StrictHostKeyChecking=no",
                f"{self.ssh_user}@{self.server_host}",
                command
            ]
            
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.warning(f"원격 명령 실행 실패: {command}, 에러: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"원격 명령 타임아웃: {command}")
            return None
        except FileNotFoundError:
            # sshpass가 없는 경우 대체 방법 시도
            logger.warning("sshpass를 찾을 수 없음. 로컬 모니터링으로 전환")
            return self._execute_local_fallback(command)
        except Exception as e:
            logger.error(f"원격 명령 실행 중 오류: {e}")
            return None
    
    def _execute_local_fallback(self, command: str) -> Optional[str]:
        """로컬 시스템에서 대체 명령 실행 (fallback)"""
        try:
            # SSH 키 기반 접속 시도
            ssh_cmd = [
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                f"{self.ssh_user}@{self.server_host}",
                command
            ]
            
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None
                
        except Exception as e:
            logger.debug(f"SSH 키 기반 접속 실패: {e}")
            return None
    
    def _get_system_stats(self) -> Optional[ResourceSnapshot]:
        """시스템 리소스 사용량 수집"""
        try:
            timestamp = time.time()
            
            # CPU 사용률
            cpu_cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | sed 's/%us,//'"
            cpu_output = self._execute_remote_command(cpu_cmd)
            cpu_percent = float(cpu_output) if cpu_output and cpu_output.replace('.', '').isdigit() else 0.0
            
            # 메모리 사용량 (MB 단위)
            mem_cmd = "free -m | grep '^Mem:' | awk '{print $3\" \"$2\" \"($3/$2*100)}'"
            mem_output = self._execute_remote_command(mem_cmd)
            if mem_output:
                mem_parts = mem_output.split()
                memory_used_mb = float(mem_parts[0]) if len(mem_parts) > 0 else 0.0
                memory_total_mb = float(mem_parts[1]) if len(mem_parts) > 1 else 0.0
                memory_percent = float(mem_parts[2]) if len(mem_parts) > 2 else 0.0
            else:
                memory_used_mb = memory_total_mb = memory_percent = 0.0
            
            # 네트워크 사용량 (MB 단위)
            net_cmd = "cat /proc/net/dev | grep -E '(eth|ens|enp)' | head -1 | awk '{print $(NF-7)\" \"$(NF-15)}'"
            net_output = self._execute_remote_command(net_cmd)
            if net_output:
                net_parts = net_output.split()
                network_recv_mb = float(net_parts[0]) / (1024*1024) if len(net_parts) > 0 else 0.0
                network_sent_mb = float(net_parts[1]) / (1024*1024) if len(net_parts) > 1 else 0.0
            else:
                network_recv_mb = network_sent_mb = 0.0
            
            # GPU 정보 (nvidia-smi가 있는 경우)
            gpu_cmd = "command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits | head -1"
            gpu_output = self._execute_remote_command(gpu_cmd)
            if gpu_output and ',' in gpu_output:
                gpu_parts = [p.strip() for p in gpu_output.split(',')]
                gpu_memory_used_mb = float(gpu_parts[0]) if len(gpu_parts) > 0 and gpu_parts[0].isdigit() else 0.0
                gpu_memory_total_mb = float(gpu_parts[1]) if len(gpu_parts) > 1 and gpu_parts[1].isdigit() else 0.0
                gpu_utilization_percent = float(gpu_parts[2]) if len(gpu_parts) > 2 and gpu_parts[2].isdigit() else 0.0
            else:
                gpu_memory_used_mb = gpu_memory_total_mb = gpu_utilization_percent = 0.0
            
            # Ollama 프로세스 리소스 사용량
            ollama_cmd = "ps aux | grep '[o]llama' | awk '{cpu+=$3; mem+=$4} END {print cpu\" \"mem}'"
            ollama_output = self._execute_remote_command(ollama_cmd)
            if ollama_output and ' ' in ollama_output:
                ollama_parts = ollama_output.split()
                ollama_process_cpu = float(ollama_parts[0]) if len(ollama_parts) > 0 else 0.0
                ollama_process_memory_mb = float(ollama_parts[1]) * memory_total_mb / 100 if len(ollama_parts) > 1 else 0.0
            else:
                ollama_process_cpu = ollama_process_memory_mb = 0.0
            
            return ResourceSnapshot(
                timestamp=timestamp,
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                memory_percent=memory_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb,
                gpu_memory_used_mb=gpu_memory_used_mb,
                gpu_memory_total_mb=gpu_memory_total_mb,
                gpu_utilization_percent=gpu_utilization_percent,
                ollama_process_cpu=ollama_process_cpu,
                ollama_process_memory_mb=ollama_process_memory_mb
            )
            
        except Exception as e:
            logger.error(f"시스템 통계 수집 중 오류: {e}")
            return None
    
    def _monitor_loop(self):
        """모니터링 루프 (별도 스레드에서 실행)"""
        logger.info(f"리소스 모니터링 시작: {self.server_host}")
        
        while self.is_monitoring:
            try:
                snapshot = self._get_system_stats()
                if snapshot:
                    self.snapshots.append(snapshot)
                    logger.debug(f"리소스 스냅샷 수집: CPU {snapshot.cpu_percent:.1f}%, MEM {snapshot.memory_percent:.1f}%")
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"모니터링 루프 오류: {e}")
                time.sleep(self.monitoring_interval)
    
    def start_monitoring(self):
        """모니터링 시작"""
        if self.is_monitoring:
            logger.warning("이미 모니터링 중입니다")
            return
        
        self.is_monitoring = True
        self.snapshots.clear()
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("리소스 모니터링 시작됨")
    
    def stop_monitoring(self) -> MonitoringSession:
        """모니터링 중지 및 결과 반환"""
        if not self.is_monitoring:
            logger.warning("모니터링이 실행 중이 아닙니다")
            return None
        
        self.is_monitoring = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        # 통계 계산
        if not self.snapshots:
            logger.warning("수집된 스냅샷이 없습니다")
            return None
        
        start_time = self.snapshots[0].timestamp
        end_time = self.snapshots[-1].timestamp
        duration = end_time - start_time
        
        # 평균/최대값 계산
        cpu_values = [s.cpu_percent for s in self.snapshots]
        memory_values = [s.memory_percent for s in self.snapshots]
        gpu_util_values = [s.gpu_utilization_percent for s in self.snapshots]
        gpu_mem_values = [s.gpu_memory_used_mb / s.gpu_memory_total_mb * 100 if s.gpu_memory_total_mb > 0 else 0 for s in self.snapshots]
        
        session = MonitoringSession(
            session_id=f"session_{int(start_time)}",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            snapshots=self.snapshots.copy(),
            avg_cpu_percent=sum(cpu_values) / len(cpu_values),
            max_cpu_percent=max(cpu_values),
            avg_memory_percent=sum(memory_values) / len(memory_values),
            max_memory_percent=max(memory_values),
            avg_gpu_utilization=sum(gpu_util_values) / len(gpu_util_values) if gpu_util_values else 0,
            max_gpu_utilization=max(gpu_util_values) if gpu_util_values else 0,
            avg_gpu_memory_percent=sum(gpu_mem_values) / len(gpu_mem_values) if gpu_mem_values else 0,
            max_gpu_memory_percent=max(gpu_mem_values) if gpu_mem_values else 0
        )
        
        logger.info(f"모니터링 세션 완료: {duration:.1f}초, {len(self.snapshots)}개 스냅샷")
        return session
    
    def print_session_summary(self, session: MonitoringSession):
        """모니터링 세션 요약 출력"""
        if not session:
            print("❌ 모니터링 세션 데이터가 없습니다")
            return
        
        print(f"\n📊 리소스 모니터링 결과 ({self.server_host})")
        print(f"{'='*50}")
        print(f"모니터링 시간: {session.duration:.1f}초")
        print(f"수집 샘플 수: {len(session.snapshots)}개")
        print(f"")
        print(f"🖥️ CPU 사용률:")
        print(f"   평균: {session.avg_cpu_percent:.1f}%")
        print(f"   최대: {session.max_cpu_percent:.1f}%")
        print(f"")
        print(f"🧠 메모리 사용률:")
        print(f"   평균: {session.avg_memory_percent:.1f}%")
        print(f"   최대: {session.max_memory_percent:.1f}%")
        
        if session.avg_gpu_utilization > 0:
            print(f"")
            print(f"🎮 GPU 사용률:")
            print(f"   GPU 활용: 평균 {session.avg_gpu_utilization:.1f}%, 최대 {session.max_gpu_utilization:.1f}%")
            print(f"   GPU 메모리: 평균 {session.avg_gpu_memory_percent:.1f}%, 최대 {session.max_gpu_memory_percent:.1f}%")
        
        # Ollama 프로세스 통계
        ollama_cpu_values = [s.ollama_process_cpu for s in session.snapshots if s.ollama_process_cpu > 0]
        ollama_mem_values = [s.ollama_process_memory_mb for s in session.snapshots if s.ollama_process_memory_mb > 0]
        
        if ollama_cpu_values:
            print(f"")
            print(f"🦙 Ollama 프로세스:")
            print(f"   CPU: 평균 {sum(ollama_cpu_values)/len(ollama_cpu_values):.1f}%")
            print(f"   메모리: 평균 {sum(ollama_mem_values)/len(ollama_mem_values):.1f}MB")
    
    def save_session_data(self, session: MonitoringSession, filepath: str):
        """세션 데이터를 JSON 파일로 저장"""
        try:
            session_dict = asdict(session)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session_dict, f, ensure_ascii=False, indent=2)
            logger.info(f"모니터링 데이터 저장됨: {filepath}")
        except Exception as e:
            logger.error(f"모니터링 데이터 저장 실패: {e}")


class LocalResourceMonitor:
    """로컬 시스템 리소스 모니터 (fallback용)"""
    
    def __init__(self, monitoring_interval: float = 2.0):
        self.monitoring_interval = monitoring_interval
        self.is_monitoring = False
        self.snapshots: List[ResourceSnapshot] = []
        self.monitor_thread: Optional[threading.Thread] = None
    
    def _get_local_stats(self) -> Optional[ResourceSnapshot]:
        """로컬 시스템 리소스 사용량 수집"""
        try:
            import psutil
            
            timestamp = time.time()
            
            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 메모리 정보
            memory = psutil.virtual_memory()
            memory_used_mb = memory.used / (1024*1024)
            memory_total_mb = memory.total / (1024*1024)
            memory_percent = memory.percent
            
            # 네트워크 정보
            net_io = psutil.net_io_counters()
            network_sent_mb = net_io.bytes_sent / (1024*1024)
            network_recv_mb = net_io.bytes_recv / (1024*1024)
            
            return ResourceSnapshot(
                timestamp=timestamp,
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                memory_percent=memory_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb
            )
            
        except ImportError:
            logger.error("psutil 패키지가 필요합니다: pip install psutil")
            return None
        except Exception as e:
            logger.error(f"로컬 시스템 통계 수집 오류: {e}")
            return None
    
    def start_monitoring(self):
        """로컬 모니터링 시작"""
        logger.info("로컬 리소스 모니터링 시작")
        # 로컬 모니터링 구현은 필요시 추가


async def main():
    """모니터 테스트 실행 예제"""
    monitor = RemoteResourceMonitor()
    
    print("🔍 리소스 모니터링 테스트 시작")
    
    # 5초간 모니터링
    monitor.start_monitoring()
    print("5초간 모니터링...")
    await asyncio.sleep(5)
    session = monitor.stop_monitoring()
    
    # 결과 출력
    monitor.print_session_summary(session)
    
    # 데이터 저장
    if session:
        monitor.save_session_data(session, "monitoring_test.json")


if __name__ == "__main__":
    asyncio.run(main())