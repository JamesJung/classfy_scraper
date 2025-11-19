#!/usr/bin/env node

/**
 * Simple MCP Server for MySQL
 * Enables Claude Code to query MySQL databases directly
 */

const mysql = require('mysql2/promise');
const readline = require('readline');

// MySQL 연결 설정
const DB_CONFIG = {
  host: process.env.MYSQL_HOST || '192.168.0.95',
  port: parseInt(process.env.MYSQL_PORT || '3309'),
  user: process.env.MYSQL_USER || 'root',
  password: process.env.MYSQL_PASSWORD || 'b3UvSDS232GbdZ42',
  database: process.env.MYSQL_DATABASE || '',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
};

let pool = null;

// MySQL 연결 풀 초기화
async function initDB() {
  try {
    pool = mysql.createPool(DB_CONFIG);
    const connection = await pool.getConnection();
    console.error('MySQL 연결 성공');
    connection.release();
  } catch (error) {
    console.error('MySQL 연결 실패:', error.message);
    throw error;
  }
}

// MCP 프로토콜 응답 전송
function sendResponse(id, result) {
  const response = {
    jsonrpc: '2.0',
    id: id,
    result: result
  };
  console.log(JSON.stringify(response));
}

// MCP 프로토콜 에러 응답 전송
function sendError(id, code, message) {
  const response = {
    jsonrpc: '2.0',
    id: id,
    error: {
      code: code,
      message: message
    }
  };
  console.log(JSON.stringify(response));
}

// SQL 쿼리 실행
async function executeQuery(sql, params = []) {
  try {
    const [rows] = await pool.execute(sql, params);
    return rows;
  } catch (error) {
    throw new Error(`쿼리 실행 실패: ${error.message}`);
  }
}

// 데이터베이스 목록 조회
async function listDatabases() {
  const rows = await executeQuery('SHOW DATABASES');
  return rows.map(row => row.Database);
}

// 테이블 목록 조회
async function listTables(database) {
  const rows = await executeQuery(`SHOW TABLES FROM \`${database}\``);
  const key = Object.keys(rows[0])[0];
  return rows.map(row => row[key]);
}

// 테이블 스키마 조회
async function describeTable(database, table) {
  const rows = await executeQuery(`DESCRIBE \`${database}\`.\`${table}\``);
  return rows;
}

// MCP 요청 처리
async function handleRequest(request) {
  const { id, method, params } = request;

  try {
    switch (method) {
      case 'initialize':
        sendResponse(id, {
          protocolVersion: '2024-11-05',
          capabilities: {
            tools: {}
          },
          serverInfo: {
            name: 'mysql-mcp-server',
            version: '1.0.0'
          }
        });
        break;

      case 'tools/list':
        sendResponse(id, {
          tools: [
            {
              name: 'query',
              description: 'Execute a SQL query',
              inputSchema: {
                type: 'object',
                properties: {
                  sql: {
                    type: 'string',
                    description: 'SQL query to execute'
                  },
                  database: {
                    type: 'string',
                    description: 'Database to use (optional)'
                  }
                },
                required: ['sql']
              }
            },
            {
              name: 'list_databases',
              description: 'List all databases',
              inputSchema: {
                type: 'object',
                properties: {}
              }
            },
            {
              name: 'list_tables',
              description: 'List all tables in a database',
              inputSchema: {
                type: 'object',
                properties: {
                  database: {
                    type: 'string',
                    description: 'Database name'
                  }
                },
                required: ['database']
              }
            },
            {
              name: 'describe_table',
              description: 'Get table schema',
              inputSchema: {
                type: 'object',
                properties: {
                  database: {
                    type: 'string',
                    description: 'Database name'
                  },
                  table: {
                    type: 'string',
                    description: 'Table name'
                  }
                },
                required: ['database', 'table']
              }
            }
          ]
        });
        break;

      case 'tools/call':
        const { name, arguments: args } = params;
        let result;

        switch (name) {
          case 'query':
            if (args.database) {
              await executeQuery(`USE \`${args.database}\``);
            }
            result = await executeQuery(args.sql);
            break;

          case 'list_databases':
            result = await listDatabases();
            break;

          case 'list_tables':
            result = await listTables(args.database);
            break;

          case 'describe_table':
            result = await describeTable(args.database, args.table);
            break;

          default:
            throw new Error(`Unknown tool: ${name}`);
        }

        sendResponse(id, {
          content: [
            {
              type: 'text',
              text: JSON.stringify(result, null, 2)
            }
          ]
        });
        break;

      default:
        sendError(id, -32601, `Method not found: ${method}`);
    }
  } catch (error) {
    console.error('Error handling request:', error);
    sendError(id, -32603, error.message);
  }
}

// 메인 함수
async function main() {
  await initDB();

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
  });

  rl.on('line', async (line) => {
    try {
      const request = JSON.parse(line);
      await handleRequest(request);
    } catch (error) {
      console.error('Failed to parse request:', error);
    }
  });

  process.on('SIGINT', async () => {
    if (pool) {
      await pool.end();
    }
    process.exit(0);
  });
}

main().catch(error => {
  console.error('Server error:', error);
  process.exit(1);
});
