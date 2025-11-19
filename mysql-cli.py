#!/usr/bin/env python3

"""
MySQL CLI Tool for Claude Code (Python version)
Usage:
  python3 mysql-cli.py query "SELECT * FROM table"
  python3 mysql-cli.py databases
  python3 mysql-cli.py tables <database>
  python3 mysql-cli.py describe <database> <table>
"""

import sys
import os
import pymysql
from pymysql.cursors import DictCursor

# MySQL 연결 설정
DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST', '192.168.0.95'),
    'port': int(os.environ.get('MYSQL_PORT', '3309')),
    'user': os.environ.get('MYSQL_USER', 'root'),
    'password': os.environ.get('MYSQL_PASSWORD', 'b3UvSDS232GbdZ42'),
    'database': os.environ.get('MYSQL_DATABASE', ''),
    'connect_timeout': 10,
    'charset': 'utf8mb4'
}

def execute_query(sql, database=None):
    """Execute SQL query and return results"""
    config = DB_CONFIG.copy()
    if database:
        config['database'] = database

    connection = pymysql.connect(**config)
    try:
        with connection.cursor(DictCursor) as cursor:
            cursor.execute(sql)
            if cursor.description:
                return cursor.fetchall()
            else:
                connection.commit()
                return []
    finally:
        connection.close()

def list_databases():
    """List all databases"""
    rows = execute_query('SHOW DATABASES')
    print('=== 데이터베이스 목록 ===')
    for row in rows:
        print(row['Database'])

def list_tables(database):
    """List all tables in a database"""
    rows = execute_query(f'SHOW TABLES', database)
    print(f'=== {database} 테이블 목록 ===')
    key = list(rows[0].keys())[0] if rows else None
    if key:
        for row in rows:
            print(row[key])

def describe_table(database, table):
    """Show table schema"""
    rows = execute_query(f'DESCRIBE `{table}`', database)
    print(f'=== {database}.{table} 스키마 ===')
    if rows:
        # Print header
        headers = list(rows[0].keys())
        print(' | '.join(headers))
        print('-' * (len(' | '.join(headers))))
        # Print rows
        for row in rows:
            print(' | '.join(str(row[h]) for h in headers))

def query(sql, database=None):
    """Execute arbitrary SQL query"""
    rows = execute_query(sql, database)

    if not rows:
        print('결과가 없습니다.')
    elif len(rows) == 1 and not rows[0]:
        print('쿼리가 성공적으로 실행되었습니다.')
    else:
        print(f'=== 쿼리 결과 ({len(rows)}행) ===')
        if rows:
            # Print header
            headers = list(rows[0].keys())
            col_widths = [max(len(str(h)), max(len(str(row[h])) for row in rows)) for h in headers]

            # Print formatted table
            header_line = ' | '.join(h.ljust(w) for h, w in zip(headers, col_widths))
            print(header_line)
            print('-' * len(header_line))

            for row in rows:
                print(' | '.join(str(row[h]).ljust(w) for h, w in zip(headers, col_widths)))

def main():
    if len(sys.argv) < 2:
        print('MySQL CLI Tool for Claude Code')
        print('')
        print('사용법:')
        print('  python3 mysql-cli.py databases              - 모든 데이터베이스 조회')
        print('  python3 mysql-cli.py tables <db>            - 테이블 목록 조회')
        print('  python3 mysql-cli.py describe <db> <table>  - 테이블 스키마 조회')
        print('  python3 mysql-cli.py query "SQL" [db]       - SQL 쿼리 실행')
        print('')
        print('예시:')
        print('  python3 mysql-cli.py databases')
        print('  python3 mysql-cli.py tables subvention')
        print('  python3 mysql-cli.py describe subvention users')
        print('  python3 mysql-cli.py query "SELECT * FROM users LIMIT 10" subvention')
        sys.exit(0)

    command = sys.argv[1]

    try:
        if command in ['databases', 'db']:
            list_databases()

        elif command in ['tables', 't']:
            if len(sys.argv) < 3:
                print('사용법: python3 mysql-cli.py tables <database>')
                sys.exit(1)
            list_tables(sys.argv[2])

        elif command in ['describe', 'desc']:
            if len(sys.argv) < 4:
                print('사용법: python3 mysql-cli.py describe <database> <table>')
                sys.exit(1)
            describe_table(sys.argv[2], sys.argv[3])

        elif command in ['query', 'q']:
            if len(sys.argv) < 3:
                print('사용법: python3 mysql-cli.py query "SELECT ..." [database]')
                sys.exit(1)
            database = sys.argv[3] if len(sys.argv) > 3 else None
            query(sys.argv[2], database)

        else:
            print(f'알 수 없는 명령어: {command}')
            sys.exit(1)

    except Exception as error:
        print(f'오류: {error}')
        sys.exit(1)

if __name__ == '__main__':
    main()
