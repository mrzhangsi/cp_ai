#!/usr/bin/env python3
"""
Redis和PostgreSQL数据查看工具
支持浏览Redis的keys和PostgreSQL的表数据
使用 psycopg (v3) 驱动
"""

import redis
import psycopg
from psycopg import sql
import json
import sys
from typing import Optional, List, Dict, Any


class DataViewer:
    """数据查看器主类"""
    
    def __init__(self):
        """初始化连接配置"""
        # Redis配置
        self.redis_config = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'decode_responses': True,
            'password': None  # 如有密码请设置
        }
        
        # PostgreSQL配置 (psycopg v3)
        self.pg_config = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'postgres',
            'user': 'postgres',
            'password': '123456'
        }
        
        self.redis_client = None
        self.pg_connection = None
        
    def connect_redis(self) -> bool:
        """连接Redis"""
        try:
            self.redis_client = redis.Redis(**self.redis_config)
            self.redis_client.ping()
            print("✓ Redis连接成功")
            return True
        except redis.ConnectionError as e:
            print(f"✗ Redis连接失败: {e}")
            return False
        except Exception as e:
            print(f"✗ Redis连接出错: {e}")
            return False
    
    def connect_postgresql(self) -> bool:
        """连接PostgreSQL (使用psycopg v3)"""
        try:
            # psycopg v3 连接方式
            conn_str = f"host={self.pg_config['host']} port={self.pg_config['port']} dbname={self.pg_config['dbname']} user={self.pg_config['user']} password={self.pg_config['password']}"
            self.pg_connection = psycopg.connect(conn_str)
            print("✓ PostgreSQL连接成功")
            return True
        except psycopg.Error as e:
            print(f"✗ PostgreSQL连接失败: {e}")
            return False
        except Exception as e:
            print(f"✗ PostgreSQL连接出错: {e}")
            return False
    
    def disconnect_all(self):
        """断开所有连接"""
        if self.redis_client:
            self.redis_client.close()
        if self.pg_connection:
            self.pg_connection.close()
        print("已断开所有连接")
    
    # ============ Redis相关方法 ============
    
    def redis_list_keys(self, pattern: str = '*', limit: int = 100) -> List[str]:
        """列出Redis中的keys"""
        try:
            keys = self.redis_client.keys(pattern)
            if len(keys) > limit:
                print(f"找到 {len(keys)} 个keys，显示前 {limit} 个")
                keys = keys[:limit]
            else:
                print(f"找到 {len(keys)} 个keys")
            return keys
        except Exception as e:
            print(f"获取keys失败: {e}")
            return []
    
    def redis_get_value(self, key: str) -> Optional[Any]:
        """获取Redis key的值"""
        try:
            key_type = self.redis_client.type(key)
            value = None
            
            if key_type == 'string':
                value = self.redis_client.get(key)
            elif key_type == 'hash':
                value = self.redis_client.hgetall(key)
            elif key_type == 'list':
                value = self.redis_client.lrange(key, 0, -1)
            elif key_type == 'set':
                value = self.redis_client.smembers(key)
            elif key_type == 'zset':
                value = self.redis_client.zrange(key, 0, -1, withscores=True)
            else:
                value = f"不支持的类型: {key_type}"
            
            return value
        except Exception as e:
            return f"获取值失败: {e}"
    
    def redis_view_key(self, key: str):
        """查看Redis某个key的详细信息"""
        print(f"\n{'='*60}")
        print(f"Key: {key}")
        print(f"类型: {self.redis_client.type(key)}")
        print(f"TTL: {self.redis_client.ttl(key)} 秒")
        
        value = self.redis_get_value(key)
        print("\n值:")
        if isinstance(value, (dict, list, set)):
            print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
        else:
            print(value)
        print(f"{'='*60}\n")
    
    def redis_interactive(self):
        """Redis交互式浏览"""
        if not self.redis_client:
            print("请先连接Redis")
            return
        
        print("\n=== Redis数据浏览 ===")
        print("命令: list [pattern] - 列出keys")
        print("      view <key> - 查看key的值")
        print("      delete <key> - 删除key")
        print("      flushdb - 清空当前数据库 (危险操作)")
        print("      back - 返回主菜单")
        print("      help - 显示帮助")
        
        while True:
            try:
                cmd = input("\nRedis > ").strip().split()
                if not cmd:
                    continue
                
                command = cmd[0].lower()
                
                if command == 'back' or command == 'exit':
                    break
                elif command == 'help':
                    print("命令: list [pattern] - 列出keys")
                    print("      view <key> - 查看key的值")
                    print("      delete <key> - 删除key")
                    print("      flushdb - 清空当前数据库")
                    print("      back - 返回主菜单")
                elif command == 'list':
                    pattern = cmd[1] if len(cmd) > 1 else '*'
                    keys = self.redis_list_keys(pattern)
                    for i, key in enumerate(keys, 1):
                        key_type = self.redis_client.type(key)
                        print(f"{i:3d}. [{key_type:6s}] {key}")
                elif command == 'view':
                    if len(cmd) < 2:
                        print("请指定key: view <key>")
                        continue
                    self.redis_view_key(cmd[1])
                elif command == 'delete':
                    if len(cmd) < 2:
                        print("请指定key: delete <key>")
                        continue
                    result = self.redis_client.delete(cmd[1])
                    print(f"删除了 {result} 个key")
                elif command == 'flushdb':
                    confirm = input("确认清空当前数据库? (yes/no): ")
                    if confirm.lower() == 'yes':
                        self.redis_client.flushdb()
                        print("数据库已清空")
                else:
                    print(f"未知命令: {command}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"错误: {e}")
    
    # ============ PostgreSQL相关方法 (psycopg v3) ============
    
    def pg_list_tables(self) -> List[str]:
        """列出所有表"""
        try:
            with self.pg_connection.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row[0] for row in cursor.fetchall()]
                print(f"找到 {len(tables)} 个表")
                return tables
        except Exception as e:
            print(f"获取表列表失败: {e}")
            return []
    
    def pg_get_table_info(self, table_name: str) -> Dict:
        """获取表结构信息"""
        try:
            with self.pg_connection.cursor() as cursor:
                # 获取列信息
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                columns = cursor.fetchall()
                
                # 获取行数 (使用psycopg的sql模块)
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                    sql.Identifier(table_name)
                ))
                row_count = cursor.fetchone()[0]
                
                return {
                    'columns': columns,
                    'row_count': row_count
                }
        except Exception as e:
            print(f"获取表信息失败: {e}")
            return {'columns': [], 'row_count': 0}
    
    def pg_view_table(self, table_name: str, limit: int = 20):
        """查看表数据"""
        try:
            info = self.pg_get_table_info(table_name)
            if not info['columns']:
                print(f"表 {table_name} 不存在或没有列")
                return
            
            print(f"\n{'='*80}")
            print(f"表名: {table_name}")
            print(f"总行数: {info['row_count']}")
            print(f"显示前 {limit} 行")
            print("\n列结构:")
            for col_name, data_type, is_nullable in info['columns']:
                nullable = 'NULL' if is_nullable == 'YES' else 'NOT NULL'
                print(f"  {col_name:20s} {data_type:20s} {nullable}")
            
            # 查询数据 (使用psycopg的sql模块)
            with self.pg_connection.cursor() as cursor:
                cursor.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(
                    sql.Identifier(table_name)
                ), (limit,))
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]
            
            print(f"\n数据 (共 {len(rows)} 行):")
            if rows:
                # 打印表头
                print("-" * 80)
                header = " | ".join([f"{name:15s}" for name in col_names])
                print(header)
                print("-" * 80)
                
                # 打印数据
                for row in rows:
                    row_str = " | ".join([
                        str(val)[:15] if val is not None else "NULL"
                        for val in row
                    ])
                    print(row_str)
                print("-" * 80)
            else:
                print("(空表)")
            
            print(f"{'='*80}\n")
            
        except Exception as e:
            print(f"查看表失败: {e}")
    
    def pg_execute_query(self, query: str):
        """执行自定义SQL查询"""
        try:
            with self.pg_connection.cursor() as cursor:
                cursor.execute(query)
                if cursor.description:
                    rows = cursor.fetchall()
                    col_names = [desc[0] for desc in cursor.description]
                    
                    print(f"\n查询结果 ({len(rows)} 行):")
                    print("-" * 80)
                    header = " | ".join([f"{name:15s}" for name in col_names])
                    print(header)
                    print("-" * 80)
                    
                    for row in rows[:50]:  # 限制显示50行
                        row_str = " | ".join([
                            str(val)[:15] if val is not None else "NULL"
                            for val in row
                        ])
                        print(row_str)
                    if len(rows) > 50:
                        print(f"... 还有 {len(rows) - 50} 行")
                    print("-" * 80)
                else:
                    print(f"执行成功，影响行数: {cursor.rowcount}")
        except Exception as e:
            print(f"查询失败: {e}")
    
    def pg_interactive(self):
        """PostgreSQL交互式浏览"""
        if not self.pg_connection:
            print("请先连接PostgreSQL")
            return
        
        print("\n=== PostgreSQL数据浏览 ===")
        print("命令: tables - 列出所有表")
        print("      view <table> [limit] - 查看表数据")
        print("      desc <table> - 查看表结构")
        print("      query <SQL> - 执行SQL查询")
        print("      back - 返回主菜单")
        print("      help - 显示帮助")
        
        while True:
            try:
                cmd = input("\nPostgreSQL > ").strip().split()
                if not cmd:
                    continue
                
                command = cmd[0].lower()
                
                if command == 'back' or command == 'exit':
                    break
                elif command == 'help':
                    print("命令: tables - 列出所有表")
                    print("      view <table> [limit] - 查看表数据")
                    print("      desc <table> - 查看表结构")
                    print("      query <SQL> - 执行SQL查询")
                    print("      back - 返回主菜单")
                elif command == 'tables':
                    tables = self.pg_list_tables()
                    for i, table in enumerate(tables, 1):
                        info = self.pg_get_table_info(table)
                        print(f"{i:3d}. {table:30s} (行数: {info['row_count']})")
                elif command == 'desc':
                    if len(cmd) < 2:
                        print("请指定表名: desc <table>")
                        continue
                    info = self.pg_get_table_info(cmd[1])
                    if info['columns']:
                        print(f"\n表: {cmd[1]}")
                        print("列信息:")
                        for col_name, data_type, is_nullable in info['columns']:
                            nullable = 'NULL' if is_nullable == 'YES' else 'NOT NULL'
                            print(f"  {col_name:20s} {data_type:20s} {nullable}")
                    else:
                        print(f"表 {cmd[1]} 不存在")
                elif command == 'view':
                    if len(cmd) < 2:
                        print("请指定表名: view <table> [limit]")
                        continue
                    table = cmd[1]
                    limit = int(cmd[2]) if len(cmd) > 2 else 20
                    self.pg_view_table(table, limit)
                elif command == 'query':
                    if len(cmd) < 2:
                        print("请提供SQL查询语句")
                        continue
                    query = ' '.join(cmd[1:])
                    self.pg_execute_query(query)
                else:
                    print(f"未知命令: {command}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"错误: {e}")
    
    # ============ 主菜单 ============
    
    def main_menu(self):
        """主菜单"""
        print("\n" + "="*50)
        print("    Redis & PostgreSQL 数据查看工具")
        print("       (使用 psycopg v3)")
        print("="*50)
        print("1. 连接Redis")
        print("2. 连接PostgreSQL")
        print("3. 连接所有数据库")
        print("4. 浏览Redis数据")
        print("5. 浏览PostgreSQL数据")
        print("6. 修改连接配置")
        print("7. 退出")
        print("="*50)
        
        while True:
            try:
                choice = input("\n请选择 (1-7): ").strip()
                
                if choice == '1':
                    self.connect_redis()
                elif choice == '2':
                    self.connect_postgresql()
                elif choice == '3':
                    self.connect_redis()
                    self.connect_postgresql()
                elif choice == '4':
                    self.redis_interactive()
                elif choice == '5':
                    self.pg_interactive()
                elif choice == '6':
                    self.edit_config()
                elif choice == '7':
                    self.disconnect_all()
                    print("再见！")
                    break
                else:
                    print("无效选择，请重新输入")
            except KeyboardInterrupt:
                self.disconnect_all()
                print("\n再见！")
                break
            except Exception as e:
                print(f"错误: {e}")
    
    def edit_config(self):
        """修改连接配置"""
        print("\n=== 修改连接配置 ===")
        print("1. Redis配置")
        print("2. PostgreSQL配置")
        print("3. 返回")
        
        choice = input("请选择: ").strip()
        
        if choice == '1':
            print(f"当前Redis配置: {self.redis_config}")
            host = input(f"Host [{self.redis_config['host']}]: ").strip()
            if host: self.redis_config['host'] = host
            port = input(f"Port [{self.redis_config['port']}]: ").strip()
            if port: self.redis_config['port'] = int(port)
            db = input(f"DB [{self.redis_config['db']}]: ").strip()
            if db: self.redis_config['db'] = int(db)
            password = input("Password (留空保持不变): ").strip()
            if password: self.redis_config['password'] = password
            print("Redis配置已更新")
            
        elif choice == '2':
            print(f"当前PostgreSQL配置: {self.pg_config}")
            host = input(f"Host [{self.pg_config['host']}]: ").strip()
            if host: self.pg_config['host'] = host
            port = input(f"Port [{self.pg_config['port']}]: ").strip()
            if port: self.pg_config['port'] = int(port)
            dbname = input(f"Database [{self.pg_config['dbname']}]: ").strip()
            if dbname: self.pg_config['dbname'] = dbname
            user = input(f"User [{self.pg_config['user']}]: ").strip()
            if user: self.pg_config['user'] = user
            password = input(f"Password: ").strip()
            if password: self.pg_config['password'] = password
            print("PostgreSQL配置已更新")


def main():
    """主函数"""
    viewer = DataViewer()
    
    try:
        viewer.main_menu()
    except KeyboardInterrupt:
        viewer.disconnect_all()
        print("\n程序已退出")
    except Exception as e:
        print(f"程序异常: {e}")
        viewer.disconnect_all()


if __name__ == "__main__":
    main()