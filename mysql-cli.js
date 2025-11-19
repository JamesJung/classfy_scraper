#!/usr/bin/env node

/**
 * MySQL CLI Tool for Claude Code
 * Usage:
 *   node mysql-cli.js query "SELECT * FROM table"
 *   node mysql-cli.js databases
 *   node mysql-cli.js tables <database>
 *   node mysql-cli.js describe <database> <table>
 */

const mysql = require('mysql2/promise');

// MySQL 연결 설정
const DB_CONFIG = {
  host: process.env.MYSQL_HOST || '192.168.0.95',
  port: parseInt(process.env.MYSQL_PORT || '3309'),
  user: process.env.MYSQL_USER || 'root',
  password: process.env.MYSQL_PASSWORD || 'b3UvSDS232GbdZ42',
  database: process.env.MYSQL_DATABASE || '',
  multipleStatements: true,
  connectTimeout: 10000,
  enableKeepAlive: true,
  keepAliveInitialDelay: 10000
};

async function executeQuery(sql, database = null) {
  const config = { ...DB_CONFIG };
  if (database) {
    config.database = database;
  }

  const connection = await mysql.createConnection(config);
  try {
    const [rows] = await connection.execute(sql);
    return rows;
  } finally {
    await connection.end();
  }
}

async function listDatabases() {
  const rows = await executeQuery('SHOW DATABASES');
  console.log('=== 데이터베이스 목록 ===');
  rows.forEach(row => console.log(row.Database));
}

async function listTables(database) {
  const rows = await executeQuery(`SHOW TABLES`, database);
  console.log(`=== ${database} 테이블 목록 ===`);
  const key = Object.keys(rows[0])[0];
  rows.forEach(row => console.log(row[key]));
}

async function describeTable(database, table) {
  const rows = await executeQuery(`DESCRIBE \`${table}\``, database);
  console.log(`=== ${database}.${table} 스키마 ===`);
  console.table(rows);
}

async function query(sql, database = null) {
  const rows = await executeQuery(sql, database);

  if (Array.isArray(rows)) {
    if (rows.length === 0) {
      console.log('결과가 없습니다.');
    } else if (rows.length === 1 && typeof rows[0] === 'object' && Object.keys(rows[0]).length === 0) {
      console.log('쿼리가 성공적으로 실행되었습니다.');
    } else {
      console.log(`=== 쿼리 결과 (${rows.length}행) ===`);
      console.table(rows);
    }
  } else {
    console.log('쿼리 결과:', rows);
  }
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  try {
    switch (command) {
      case 'databases':
      case 'db':
        await listDatabases();
        break;

      case 'tables':
      case 't':
        if (!args[1]) {
          console.error('사용법: node mysql-cli.js tables <database>');
          process.exit(1);
        }
        await listTables(args[1]);
        break;

      case 'describe':
      case 'desc':
        if (!args[1] || !args[2]) {
          console.error('사용법: node mysql-cli.js describe <database> <table>');
          process.exit(1);
        }
        await describeTable(args[1], args[2]);
        break;

      case 'query':
      case 'q':
        if (!args[1]) {
          console.error('사용법: node mysql-cli.js query "SELECT ..." [database]');
          process.exit(1);
        }
        await query(args[1], args[2]);
        break;

      default:
        console.log('MySQL CLI Tool for Claude Code');
        console.log('');
        console.log('사용법:');
        console.log('  node mysql-cli.js databases              - 모든 데이터베이스 조회');
        console.log('  node mysql-cli.js tables <db>            - 테이블 목록 조회');
        console.log('  node mysql-cli.js describe <db> <table>  - 테이블 스키마 조회');
        console.log('  node mysql-cli.js query "SQL" [db]       - SQL 쿼리 실행');
        console.log('');
        console.log('예시:');
        console.log('  node mysql-cli.js databases');
        console.log('  node mysql-cli.js tables subvention');
        console.log('  node mysql-cli.js describe subvention users');
        console.log('  node mysql-cli.js query "SELECT * FROM users LIMIT 10" subvention');
        process.exit(0);
    }
  } catch (error) {
    console.error('오류:', error.message);
    process.exit(1);
  }
}

main();
