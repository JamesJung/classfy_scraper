#!/usr/bin/env python3
"""
MySQL 연결 수 확인 및 관리 스크립트
"""

import pymysql
import os
from dotenv import load_dotenv
from tabulate import tabulate
import sys

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

def check_connections():
    """MySQL 연결 정보 확인"""
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with conn.cursor() as cursor:
            print("=" * 80)
            print("MySQL 연결 수 정보")
            print("=" * 80)
            
            # 1. 최대 연결 수 설정
            cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
            result = cursor.fetchone()
            max_conn = result.get('Value') if isinstance(result, dict) else result[1] if result else 'Unknown'
            print(f"\n📊 최대 연결 수: {max_conn}")
            
            # 2. 현재 연결 수
            cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
            result = cursor.fetchone()
            current_conn = result.get('Value') if isinstance(result, dict) else result[1] if result else '0'
            print(f"📈 현재 연결 수: {current_conn}/{max_conn}")
            
            # 3. 최대 동시 연결 기록
            cursor.execute("SHOW STATUS LIKE 'Max_used_connections'")
            result = cursor.fetchone()
            max_used = result.get('Value') if isinstance(result, dict) else result[1] if result else '0'
            print(f"📝 최대 동시 연결 기록: {max_used}")
            
            # 4. 연결 오류 횟수
            cursor.execute("SHOW STATUS LIKE 'Connection_errors_max_connections'")
            result = cursor.fetchone()
            conn_errors = result.get('Value') if isinstance(result, dict) else result[1] if result else '0'
            print(f"❌ 연결 제한 초과 오류: {conn_errors}회")
            
            # 5. 사용률 계산
            usage = (int(current_conn) / int(max_conn)) * 100
            print(f"📊 연결 사용률: {usage:.1f}%")
            
            if usage > 80:
                print("⚠️ 경고: 연결 사용률이 80%를 초과했습니다!")
            
            # 6. 현재 연결 목록
            print("\n" + "=" * 80)
            print("현재 연결 목록")
            print("=" * 80)
            
            cursor.execute("SHOW FULL PROCESSLIST")
            processes = cursor.fetchall()
            
            if processes:
                # 테이블 형태로 출력
                table_data = []
                for proc in processes[:10]:  # 상위 10개만
                    table_data.append([
                        proc.get('Id', ''),
                        proc.get('User', ''),
                        proc.get('Host', '').split(':')[0],  # IP만 표시
                        proc.get('db', '') or 'NULL',
                        proc.get('Command', ''),
                        proc.get('Time', ''),
                        str(proc.get('State', ''))[:30],  # 상태 짧게
                    ])
                
                headers = ['ID', 'User', 'Host', 'DB', 'Command', 'Time', 'State']
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
                
                if len(processes) > 10:
                    print(f"\n... 외 {len(processes) - 10}개 연결")
            
            # 7. 사용자별 연결 수
            print("\n" + "=" * 80)
            print("사용자별 연결 수")
            print("=" * 80)
            
            cursor.execute("""
                SELECT user, 
                       SUBSTRING_INDEX(host, ':', 1) as host_ip,
                       COUNT(*) as connections
                FROM information_schema.processlist
                GROUP BY user, host_ip
                ORDER BY connections DESC
            """)
            
            user_conns = cursor.fetchall()
            if user_conns:
                table_data = [[u['user'], u['host_ip'], u['connections']] for u in user_conns]
                print(tabulate(table_data, headers=['User', 'Host', 'Connections'], tablefmt='grid'))
            
            # 8. 추천사항
            print("\n" + "=" * 80)
            print("추천사항")
            print("=" * 80)
            
            if int(current_conn) > int(max_conn) * 0.8:
                print("⚠️ 연결 수가 한계에 가까워지고 있습니다.")
                print(f"   권장: SET GLOBAL max_connections = {int(max_conn) * 2};")
                
            if int(conn_errors) > 0:
                print(f"⚠️ 연결 오류가 {conn_errors}회 발생했습니다.")
                print("   max_connections를 늘려야 합니다.")
                
            print("\nMySQL 설정 변경 방법:")
            print("1. 임시 변경 (재시작시 초기화):")
            print(f"   SET GLOBAL max_connections = 500;")
            print("\n2. 영구 변경 (my.cnf 또는 my.ini 파일):")
            print("   [mysqld]")
            print("   max_connections = 500")
            print("   max_user_connections = 50")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        print("\n대신 서버에서 직접 실행하세요:")
        print(f"mysql -h {DB_HOST} -P {DB_PORT} -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} < check_mysql_connections.sql")

if __name__ == "__main__":
    check_connections()