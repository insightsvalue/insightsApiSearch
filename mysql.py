from sqlalchemy import create_engine
import pandas as pd
import datetime
import pymysql
import numpy as np

class Mysql:
    def __init__(self, username, password, host, port, database):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self.create_database()
        self.engine = create_engine(
            f'mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?charset=utf8')
        self.create_tables()
        # self.con = self.engine.connect()

    def create_database(self):
        with pymysql.connect(host=self.host, user=self.username, password=self.password,
                             cursorclass=pymysql.cursors.DictCursor) as con:
            with con.cursor() as cur:
                cur.execute(f'CREATE DATABASE IF NOT EXISTS `{self.database}`')

    def create_tables(self):
        """
        t_base_project中包含个人项目和组项目
        """
        t_base_project = 'CREATE TABLE IF NOT EXISTS t_base_project(' \
                         '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                         '`created_at` TIMESTAMP NOT NULL,' \
                         '`updated_at` TIMESTAMP NOT NULL,' \
                         '`is_deleted` TINYINT NOT NULL,' \
                         '`name` VARCHAR(64) NOT NULL,' \
                         '`git_id` INT NOT NULL,' \
                         '`description` VARCHAR(255),' \
                         '`domain` VARCHAR(256) NOT NULL,' \
                         '`kind` VARCHAR(32),' \
                         '`owner` VARCHAR(32),' \
                         '`web_url` VARCHAR(255) NOT NULL,' \
                         '`git_url` VARCHAR(255) NOT NULL)'

        t_rel_project_user = 'CREATE TABLE IF NOT EXISTS t_rel_project_user(' \
                             '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                             '`created_at` TIMESTAMP NOT NULL,' \
                             '`updated_at` TIMESTAMP NOT NULL,' \
                             '`project_id` INT NOT NULL,' \
                             '`user_id` INT,' \
                             '`notice` TINYINT(1) DEFAULT 1)' \

        t_rel_project_group = 'CREATE TABLE IF NOT EXISTS t_rel_project_group(' \
                              '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                              '`created_at` TIMESTAMP NOT NULL,' \
                              '`updated_at` TIMESTAMP NOT NULL,' \
                              '`project_id` INT NOT NULL,' \
                              '`group_id` INT NOT NULL)' \

        t_rel_group_user = 'CREATE TABLE IF NOT EXISTS t_rel_group_user(' \
                           '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                           '`created_at` TIMESTAMP NOT NULL,' \
                           '`updated_at` TIMESTAMP NOT NULL,' \
                           '`group_id` INT NOT NULL,' \
                           '`user_id` INT NOT NULL)' \

        t_base_user = 'CREATE TABLE IF NOT EXISTS t_base_user(' \
                      '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                      '`created_at` TIMESTAMP NOT NULL,' \
                      '`updated_at` TIMESTAMP NOT NULL,' \
                      '`username` VARCHAR(32) NOT NULL,' \
                      '`name` VARCHAR(32) NOT NULL,' \
                      '`git_id` INT NOT NULL,' \
                      '`mobile` VARCHAR(16),' \
                      '`email` VARCHAR(128) NOT NULL,' \
                      '`web_url` VARCHAR(255) NOT NULL)'

        t_base_group = 'CREATE TABLE IF NOT EXISTS t_base_group(' \
                       '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                       '`created_at` TIMESTAMP NOT NULL,' \
                       '`updated_at` TIMESTAMP NOT NULL,' \
                       '`name` VARCHAR(32) NOT NULL,' \
                       '`git_id` INT NOT NULL,' \
                       '`description` VARCHAR(128) NOT NULL,' \
                       '`web_url` VARCHAR(255) NOT NULL)' \

        t_log_project = 'CREATE TABLE IF NOT EXISTS t_log_project(' \
                        '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                        '`created_at` TIMESTAMP NOT NULL,' \
                        '`updated_at` TIMESTAMP NOT NULL,' \
                        '`project_id` INT NOT NULL,' \
                        '`content` TEXT NOT NULL)'

        t_inspect_batch = 'CREATE TABLE IF NOT EXISTS t_inspect_batch(' \
                          '`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                          '`created_at` TIMESTAMP NOT NULL,' \
                          '`updated_at` TIMESTAMP NOT NULL,' \
                          '`project_id` INT NOT NULL)' \

        t_inspect_details = 'CREATE TABLE IF NOT EXISTS t_inspect_details(' \
                            '`id` BIGINT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,' \
                            '`created_at` TIMESTAMP NOT NULL,' \
                            '`updated_at` TIMESTAMP NOT NULL,' \
                            '`batch_id` INT NOT NULL,' \
                            '`file_name` VARCHAR(64) NOT NULL,' \
                            '`file_path` VARCHAR(1024) NOT NULL,' \
                            '`git_commit_id` VARCHAR(64) NOT NULL,' \
                            '`error_msg` VARCHAR(512) NOT NULL,' \
                            '`error_code` VARCHAR(128) NOT NULL,' \
                            '`error_type` VARCHAR(128) NOT NULL,' \
                            '`location` VARCHAR(128) NOT NULL,' \
                            '`content` VARCHAR(512) NOT NULL)' \

        t_login_user = 'CREATE TABLE IF NOT EXISTS t_login_user(' \
                       '`username` VARCHAR(64) NOT NULL,' \
                       '`token` VARCHAR(512) NOT NULL)'

        create_table_sqls = [t_base_project,
                             t_base_user,
                             t_base_group,
                             t_rel_project_user,
                             t_rel_group_user,
                             t_rel_project_group,
                             t_inspect_batch,
                             t_inspect_details,
                             t_log_project,
                             t_login_user
                             ]

        with self.engine.connect() as con:
            for sql in create_table_sqls:
                con.execute(sql)

    def df_filter(self, df, table, filter_key='id'):
        """
        根据字段去重
        :param filter_key:
        :param df:
        :param table:
        :param key:
        :return:
        """
        with self.engine.connect() as con:
            old_df = pd.read_sql(f'select * from {table}', con=con)
            filtered_df = pd.DataFrame()
            print(table, '原数据量:', len(old_df))
            if type(filter_key) == list:
                # 多个key去重
                column_values = []
                for column in filter_key:
                    values = old_df[column].to_list()
                    column_values.append(values)
                values = []
                for i in range(len(column_values[0])):
                    tmp = []
                    for value in column_values:
                        tmp.append(value[i])
                    values.append(tmp)
                for i, row in df.iterrows():
                    row_values = row[filter_key].to_list()
                    if row_values not in values:
                        filtered_df = filtered_df.append(row)
            else:
                old_keys = list(old_df[filter_key])
                filtered_df = df[~df[filter_key].isin(old_keys)]
        print(table, '入库数量:', len(filtered_df))
        return filtered_df

    def insert_t_base_project(self, df):
        table = 't_base_project'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, 'git_id')
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_base_user(self, df):
        table = 't_base_user'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, 'git_id')
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_base_group(self, df):
        table = 't_base_group'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, 'git_id')
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_rel_project_user(self, df):
        table = 't_rel_project_user'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, 'project_id')
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_rel_project_group(self, df):
        table = 't_rel_project_group'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, 'project_id')
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_rel_group_user(self, df):
        table = 't_rel_group_user'
        with self.engine.connect() as con:
            df = self.df_filter(df, table, ['group_id', 'user_id'])
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_inspect_batch(self, project_id):
        """
        t_inspect_batch表个只允许一次入库一条数据
        先用用project的git_id查到project_id,
        拿着project_id入库
        再用created_at查找刚才入库t_inspect_batch的那条数据自增的id字段,
        id字段需要作为batch_id提交给insert_t_inspect_detail使用
        """
        table = 't_inspect_batch'
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.engine.connect() as con:
            sql = f'select id from t_base_project where git_id={project_id}'
            sql_df = pd.read_sql(sql, con=con)
            if len(sql_df) != 1:
                raise Exception(f'The number of "{sql}" result is not 1!')

            project_id = sql_df['id'].iloc[0]
            data = {
                'created_at': now_str,
                'updated_at': now_str,
                'project_id': project_id
            }
            df = pd.DataFrame([data])
            # df = self.df_filter(df, table, 'created_at')
            df.to_sql(name=table, con=con, if_exists='append', index=False)
            sql = f'select max(id) from t_inspect_batch where project_id="{project_id}"'
            sql_df = pd.read_sql(sql, con=con)
            if len(sql_df) != 1:
                raise Exception(f'The number of "{sql}" result is not 1!')

            batch_id = sql_df['max(id)'].iloc[0]

        return batch_id

    def insert_t_inspect_details(self, df):
        table = 't_inspect_details'
        with self.engine.connect() as con:
            print(table, '入库数量:', len(df))
            df.to_sql(name=table, con=con, if_exists='append', index=False)

    def insert_t_log_project(self, df):
        pass

    def insert_t_base_api(self, df):
        table = 't_base_api'
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['id'] = range(len(df))
        df['created_at'] = now_str
        df['updated_at'] = now_str
        with self.engine.connect() as con:
            print(table, '入库数量:', len(df))
            df.to_sql(name=table, con=con, if_exists='replace', index=False)

    def insert_t_base_database_url(self, df):
        table = 't_base_database_url'
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['id'] = range(len(df))
        df['created_at'] = now_str
        df['updated_at'] = now_str
        with self.engine.connect() as con:
            print(table, '入库数量:', len(df))
            df.to_sql(name=table, con=con, if_exists='replace', index=False)

    def insert_t_rel_project_host(self, df):
        table = 't_rel_project_host'
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['id'] = range(len(df))
        df['created_at'] = now_str
        df['updated_at'] = now_str
        with self.engine.connect() as con:
            print(table, '入库数量:', len(df))
            df.to_sql(name=table, con=con, if_exists='replace', index=False)

# mysql = Mysql('root', '19970429', 'localhost', '3306', 'gitlab_checker')
# mysql.init_tables()
