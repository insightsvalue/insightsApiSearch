import os
import re
import json
import chardet
import gitlab
import requests
import base64
import zipfile
import datetime
from tqdm import tqdm
import matplotlib.pyplot as plt
import pandas as pd
from bs4 import BeautifulSoup
from utils.extractor import Extractor, FilePathException
import psutil
import threading
from mysql import Mysql
from glob import glob
from configparser import ConfigParser

class NoCommitException(Exception):
    def __init__(self, project_name):
        self.project_name = project_name

    def __str__(self):
        return (f'project {self.project_name} has no commit!')


class SameNameException(Exception):
    # 有同名仓库的问题，后续打算用project_id作为参数
    def __init__(self, project_name):
        self.project_name = project_name

    def __str__(self):
        return (f'{self.project_name} has SameNameException!')


def get_encoding(file):
    with open(file, 'rb') as f:
        data = f.read()
        return chardet.detect(data)['encoding']


class GitLabChecker:
    def __init__(self):
        """
        入库程序需要用到多进程来避免pylint自身的内存溢出问题(占用内存会随着程序运行时间一直增大)，
        multiprocessing有个比较坑爹的地方就是它会用pickle来序列化一些数据，
        因为要把数据复制到新spawn出来的进程。
        tps://mikolaje.github.io/2019/sqlalchemy_with_multiprocess.html
        """
        self.load_config()
        self.download_path = os.path.join(os.path.dirname(__file__), 'download_file')
        self.fig_path = os.path.join(os.path.dirname(__file__), 'fig')
        self.frontend_api_path = os.path.join(os.path.dirname(__file__), 'frontend_api')
        self.backend_api_path = os.path.join(os.path.dirname(__file__), 'backend_api')
        self.database_url_path = os.path.join(os.path.dirname(__file__), 'database_url')
        self.data_path = os.path.join(os.path.dirname(__file__), 'data')
        self.api_path = os.path.join(self.data_path, 'api.csv')
        self.database_url_file_path = os.path.join(self.data_path, 'database_url.csv')
        self.init_folder_path(ignore=['backend_api_path', 'frontend_api_path', 'data_path', 'database_url_path'])
        self.gl = gitlab.Gitlab(self.base_url, oauth_token=self.token)
        self.gl_upload = gitlab.Gitlab(self.base_url, oauth_token=self.upload_token)
        self.projects = sorted(self.gl.projects.list(all=True), key=lambda x: x.id)
        self.users = sorted(self.gl.users.list(all=True), key=lambda x: x.id)
        self.groups = sorted(self.gl.groups.list(all=True), key=lambda x: x.id)
        self.init_tables()
        print('GitLabChecker init success!')

    def load_config(self):
        cfg = ConfigParser()
        cfg.read("config.ini")
        gitlab_cfg = dict(cfg.items('gitlab'))
        mysql_cfg = dict(cfg.items('mysql'))
        self.base_url = gitlab_cfg['base_url']
        self.token = gitlab_cfg['token']
        self.upload_token = gitlab_cfg['upload_token']
        mysql_instance = Mysql(mysql_cfg['user'], mysql_cfg['password'], mysql_cfg['host'], mysql_cfg['port'], mysql_cfg['database'])
        self.mysql = mysql_instance

    def init_folder_path(self, ignore=['backend_api_path', 'frontend_api_path', 'data_path', 'database_url_path']):

        path_dict = {
            'download_path': self.download_path,
            'frontend_api_path': self.frontend_api_path,
            'backend_api_path': self.backend_api_path,
            'database_url_path': self.database_url_path,
            'fig_path': self.fig_path,
            'data_path': self.data_path
        }

        for path_name in path_dict.keys():
            folder = path_dict[path_name]
            if path_name in ignore:
                if not os.path.exists(folder):
                    os.mkdir(folder)
            else:
                os.system(f'rm -rf {folder}')
                os.mkdir(folder)

    def init_tables(self):
        # 插入数据到基础表
        self.insert_t_base_project()
        self.insert_t_base_user()
        self.insert_t_base_group()
        self.insert_t_rel_project_user()
        self.insert_t_rel_project_group()
        self.insert_t_rel_group_user()
        self.insert_t_base_api()
        self.insert_t_base_database_url()

    def get_project_by_id(self, project_id):
        for project in self.projects:
            if project.id == project_id:
                return project
        raise Exception(f'No project id is {project_id}')

    def get_project_by_name(self, project_name):
        # 注意这里有重名的project，推荐使用get_project_by_id
        for project in self.projects:
            if project.name == project_name:
                return project
        raise Exception(f'No project named {project_name}')

    def get_project_path_by_id(self, project_id):
        for project in self.projects:
            if project.id == project_id:
                return project.path
        raise Exception(f'No project id is {project_id}')

    def get_commits(self, project_id, all=False):
        project = self.get_project_by_id(project_id)
        commits = project.commits.list(all=all)
        commit_dict = {}
        for commit in commits:
            date = commit.authored_date.replace('.000+08:00', '').replace('T', ' ').replace('%20', ' ')
            _, _, _, name, project, _, _, commit_id = commit.web_url.split('/')
            url = f'{self.base_url}{name}/{project}/-/archive/{commit_id}/{project}-{commit_id}.zip'
            commit_dict[date] = url
        return commit_dict

    def download_commit(self, project_id, commit_id, output_path):
        project = self.get_project_by_id(project_id)
        zip = project.repository_archive(sha=commit_id, format='zip')
        with open(output_path, 'wb') as f:
            f.write(zip)

    def unzip(self, zip_path, out_path):
        """
        zip包中是一个最外层以commit_id的命名的文件夹，入库需要简洁的文件路径，所有这里要替换成project_name
        :param zip_path: zip的路径
        :param out_path: 解压后的路径
        :return:
        """
        zip_file = zipfile.ZipFile(zip_path)
        zip_list = zip_file.namelist()

        if os.path.exists(out_path):
            os.system(f"rm -rf '{out_path}'")

        commit_dir = os.path.join(self.download_path, zip_list[0])

        for f in zip_list[1:]:
            zip_file.extract(f, self.download_path)
        zip_file.close()
        os.system(f"mv '{commit_dir}' '{out_path}'")

    def unzip_time_dir(self, zip_path, out_path):
        """
        将每个commit的文件夹以时间命名
        :param zip_path: zip的路径
        :param out_path: 解压后的路径
        :return:
        """
        zip_file = zipfile.ZipFile(zip_path)
        zip_list = zip_file.namelist()
        if not os.path.exists(out_path):
            os.makedirs(out_path)
        else:
            os.system(f"rm -rf '{out_path}'")
            os.makedirs(out_path)

        commit_dir = os.path.join(self.download_path, zip_list[0])

        for f in zip_list[1:]:
            zip_file.extract(f, self.download_path)
        zip_file.close()

        os.system(f"mv '{commit_dir}' '{out_path}'")

    def check_single_commit(self, project_id, commit_id, rename_to_authored_date=False, upload=False):
        """
        下载每个commit的zip包，并解压，最后审查出报告，返回DataFrame
        upload参数：是否将报告上传至gitlab
        rename_to_authored_date: 值True时，文件夹以时间命名；为False时，文件夹以项目名称命名
        """

        def parse(extractor_path, commit_id):
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            datas = []
            with open(extractor_path, 'r', encoding=get_encoding(extractor_path)) as f:
                lines = f.readlines()
                for line in lines:
                    info = self.parse_line(line)
                    if info == None:
                        continue
                    if len(line) > 512:
                        # 莫名其妙会出现很长的，不入库
                        continue
                    data = {
                        'created_at': now_str,
                        'updated_at': now_str,
                        'batch_id': None,
                        'file_name': os.path.basename(info['filename']),
                        'file_path': info['filename'].replace('download_file/', ''),
                        'git_commit_id': commit_id,
                        'error_msg': info['error_msg'].strip(),
                        'error_code': info['error_code'].strip(),
                        'error_type': info['error_type'].strip(),
                        'location': info['location'].strip(),
                        'content': line
                    }
                    datas.append(data)
            df = pd.DataFrame(datas)
            return df

        project = self.get_project_by_id(project_id)
        commits = project.commits.list(all=True)
        commit = None
        for _ in commits:
            if _.id == commit_id:
                commit = _

        if commit == None:
            raise Exception(f'{project.name} has no commit_id: {commit_id}')

        # _, _, _, name, project, _, _, commit_id = commit.web_url.split('/')
        zip_path = os.path.join(self.download_path, 'tmp.zip')

        if rename_to_authored_date:
            # 2022-04-12 09:34:10.000+00:00 2022-04-12 18:49:40 两种情况
            commit_time = commit.authored_date.split('.')[0].replace('.000+08:00', '').replace('T', ' ').replace('%20',
                                                                                                                 ' ')
            dir_path = os.path.join(self.download_path, project.name, commit_time)
            extractor_path = os.path.join(self.download_path, f'{commit_time}.txt')
            self.download_commit(project_id=project_id, commit_id=commit.id, output_path=zip_path)
            self.unzip_time_dir(zip_path, dir_path)
        else:
            dir_path = os.path.join(self.download_path, project.name)
            extractor_path = os.path.join(self.download_path, f'{project.name}.txt')
            self.download_commit(project_id=project_id, commit_id=commit.id, output_path=zip_path)
            self.unzip(zip_path, dir_path)

        extractor = Extractor(filepath=dir_path)
        extractor.check(if_print=False, if_csv=False)

        if upload:
            gitlab_file_path = self.upload_file_to_ysrd_extractor_report(project.name, extractor_path)

        data = parse(extractor_path, commit_id)
        return data

    def check_project_latest_commit(self, project_id):
        """
        审查项目最新commit
        """
        project = self.get_project_by_id(project_id)
        commits = project.commits.list()
        if len(commits) == 0:
            raise NoCommitException(project.name)
        latest_commit_id = commits[0].id
        data = self.check_single_commit(project_id, latest_commit_id)
        return data

    def check_project(self, project_id, rename_to_authored_date=False, all=False, upload=False):
        """
        审查项目所有commit
        rename_to_authored_date: 如果用来画图时，应为True
        """
        project = self.get_project_by_id(project_id)
        commits = project.commits.list(all=all)
        datas = []
        for commit in tqdm(commits):
            data = self.check_single_commit(project.name, commit.id, rename_to_authored_date=rename_to_authored_date,
                                            upload=upload)
            datas.append(data)
        return datas

    def check_project_commit_and_insert(self, project_id, commit_id):
        """
        审查某个commit并入库
        """
        with self.mysql.engine.connect() as con:
            sql = f'select id from t_base_project where git_id="{project_id}"'
            sql_df = pd.read_sql(sql, con=con)
            if len(sql_df) != 1:
                raise Exception(f'The number of "{sql}" result is not 1!')

            df = self.check_single_commit(project_id, commit_id)
            if len(df) == 0:
                # 没有detail就不入库了
                return
            batch_id = self.insert_t_inspect_batch(project_id)
            df['batch_id'] = batch_id
            self.mysql.insert_t_inspect_details(df)

    def check_project_latest_commit_and_insert(self, project_id):
        """
        审查项目最新的一个commit并入库
        先通过insert_t_inspect_batch插入一条数据，并获取一个batch_id
        然后在用extractor生成报告并解析入库
        这里为了测试程序时避免重复入库，在入库时候检查三天之内此库有没有其他的检查记录
        先获取该project的project_id，查取t_inspect_batch表中最新created_at字段，
        与现在时间进行对比，如果超过约定的间隔时间则不审查，不入库

        这里为了测试程序时避免重复入库，在入库时候检查三天之内此库有没有其他的检查记录
        先获取该project的project_id，查取t_inspect_batch表中最新created_at字段，
        与现在时间进行对比，如果超过约定的时间
        """
        project = self.get_project_by_id(project_id)
        commits = project.commits.list()
        if len(commits) == 0:
            raise NoCommitException(project.name)
        with self.mysql.engine.connect() as con:
            sql = f'select id from t_base_project where git_id="{project_id}"'
            sql_df = pd.read_sql(sql, con=con)
            if len(sql_df) != 1:
                raise Exception(f'The number of "{sql}" result is not 1!')

            project_idx = sql_df['id'].iloc[0]
            sql = f'select created_at from t_inspect_batch where project_id="{project_idx}" order by created_at limit 1'
            sql_df = pd.read_sql(sql, con=con)

            commits = project.commits.list()
            if len(commits) == 0:
                raise NoCommitException(project.name)
            else:
                latest_commit_id = commits[0].id

            if len(sql_df) == 0:
                # 该project没有审查记录，直接插入数据
                self.check_project_commit_and_insert(project_id, latest_commit_id)
            else:
                # 检查20个小时前是否有审查，否则插入数据
                last_created_at = sql_df['created_at'].iloc[0]
                now = datetime.datetime.now()
                interval_hour = (now - last_created_at).components.hours
                if interval_hour < 20:
                    print(f'仓库:{project.name} 上次审查时间小于20个小时，这次不做入库处理')
                else:
                    self.check_project_commit_and_insert(project_id, latest_commit_id)

    def check_all_project_latest_commit_and_insert(self):
        for project in tqdm(self.projects):
            try:
                self.init_folder_path()
                print(f'checking {project.name}...')
                self.check_project_latest_commit_and_insert(project.id)
                # print('主进程：',os.getpid(),'当前进程的内存使用：%.4f M' % (psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024))
            except NoCommitException as e:
                # 这里catch住没有commit的仓库，不报错，不入库
                print(e)
            except FilePathException as e:
                # 路径问题
                print(e)
            except zipfile.BadZipFile as e:
                # 有些zip包是坏的
                print(e)
            except UnicodeDecodeError as e:
                # 文件编码问题
                print(e)
            except gitlab.exceptions.GitlabListError as e:
                # gitlab内部错误
                print(e)

    def check_project_commits_and_insert(self, project_id, commit_length):
        """
        这个函数只是来配合测试画图的，慎用，会破坏数据表
        """
        project = self.get_project_by_id(project_id)
        commits = project.commits.list(all=True)[:commit_length]
        for commit in tqdm(commits):
            self.init_folder_path()
            try:
                print(f'checking {project.name} {commit.id}...')
                self.check_project_commit_and_insert(project.id, commit.id)
            except NoCommitException as e:
                # 这里catch住没有commit的仓库，不报错，不入库
                print(e)
            except FilePathException as e:
                # 路径问题
                print(e)
            except zipfile.BadZipFile as e:
                # 有些zip包是坏的
                print(e)
            except UnicodeDecodeError as e:
                # 文件编码问题
                print(e)

    def parse_line(self, line):
        """
        从报告中解析
        """
        if '.py' not in line:
            return None
        if line.count(':') == 2:
            file, lineno, info = line.split(':')
        elif line.count(':') == 3:
            file, lineno, code, info = line.split(':')
        elif line.count(':') == 4:
            file, lineno, indent, code, info = line.split(':')
        else:
            return None

        if 'indent' in locals().keys():
            lineno += ':' + indent
        error_type = re.findall('\(.*?\)', line)[-1].replace('(', '').replace(')', '')
        data = {
            'filename': file,
            'location': lineno,
            'error_msg': info,
            'error_code': code,
            'error_type': error_type
        }
        return data

    def plot_from_gitlab(self, project_id, all=False):
        # 暂时因为self.parse适配新的目录结构，不可用了,后续统一改为从数据库中读取
        """
        从gitlab下载报告再画图,
        需要使用
        gitlabchecker.check_project(project_name, rename_to_authored_date=True, upload=True)
        先将报告上传至gitlab
        """

        def count_mistakes(lines):
            datas = []
            for line in lines:
                data = self.parse_line(line)
                if data != None:
                    datas.append(data)

            if len(datas) != 0:
                df = pd.DataFrame(datas)
                df_stat = pd.DataFrame()
                df_stat['error_type'] = list(df['error_type'].value_counts().index)
                df_stat['time'] = list(df['error_type'].value_counts().values)
                df_stat['error_code'] = list(df['error_code'].value_counts().index)
            else:
                df_stat = pd.DataFrame()
                df_stat['error_type'] = []
                df_stat['time'] = []
                df_stat['error_code'] = []
            return df_stat

        def get_report_paths(project_id, suffix='.txt', path='', all=False):
            """
            获得报告的路径
            """
            project = self.get_project_by_id(project_id)
            files = project.repository_tree(all=all, recursive=True, path=path, as_list=True)
            report_paths = [file['path'] for file in files if os.path.splitext(file['path'])[-4:][-1] == suffix]
            return report_paths

        def get_file_content(project_id, file_path):
            """
            获取仓库里某个文件的每行文本，返回数组
            """
            project = self.get_project_by_id(project_id)
            blames = project.files.blame(
                file_path=file_path, ref="master")
            # 这里之前好想遇到过blames的长度大于1的情况，如果遇到画图情况出问题应该检查这个blames的长度
            lines = blames[0]['lines']
            return lines

        project_path = self.get_project_path_by_id(project_id)
        project = self.get_project_by_id(project_id)
        ysrd_extractor_report = self.get_project_by_name('ysrd-extractor-report')
        report_paths = get_report_paths(ysrd_extractor_report.id, path=project_path, all=all)
        commit_times = [os.path.splitext(os.path.basename(filepath))[0].split(' ')[0] for filepath in report_paths]

        dfs = []
        for report_path in tqdm(report_paths):
            lines = get_file_content(ysrd_extractor_report.id, file_path=report_path)
            df_tmp = count_mistakes(lines)
            dfs.append(df_tmp)

        error_types = set()
        for df in dfs:
            for error_type in df['error_type']:
                error_types.add(error_type)

        result = {}
        for df in dfs:
            for error_type in error_types:
                df_error = df[df['error_type'] == error_type]
                if len(df_error) == 0:
                    error_time = 0
                elif len(df_error) == 1:
                    error_time = df_error['time'].iloc[0]
                else:
                    raise Exception('count error error!')
                if error_type not in result.keys():
                    result[error_type] = [error_time]
                else:
                    result[error_type].append(error_time)

        fig = plt.figure(figsize=(24, 12))
        fig.suptitle(f'{project.name}近{len(report_paths)}次commit ysrd-extractor报告', fontsize=20)

        plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=1, hspace=0.5)
        for i, key in enumerate(result.keys()):
            ax1 = plt.subplot(7, 8, i + 1)
            values = result[key]
            ax1.plot(range(len(values)), values, linewidth=2.0, label=key)
            ax1.set_xticks([0, 19])
            ax1.set_xticklabels([commit_times[0], commit_times[-1]])
            ax1.set_title(key)
        fig_name = os.path.join(self.download_path, f'{project.name}统计.png')
        plt.savefig(fig_name)
        return fig_name

    def insert_t_base_project(self):
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for project in self.projects:
            # if not hasattr(project,'owner'):
            #     owner = None
            # else:
            #     owner = project.owner['username']
            data = {
                'git_id': project.id,
                'created_at': now_str,
                'updated_at': now_str,
                'is_deleted': 0,
                'name': project.name,
                'description': project.description,
                'domain': self.base_url,
                'kind': project.namespace['kind'],
                'owner': None,  # 这个字段跟devloper和group没关系，属于新建project的时候由人工填写
                'web_url': project.web_url,
                'git_url': project.http_url_to_repo
            }
            datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_base_project(df)

    def insert_t_base_user(self):
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for user in self.users:
            data = {
                'created_at': now_str,
                'updated_at': now_str,
                'username': user.username,
                'name': user.name,
                'git_id': user.id,
                'mobile': None,
                'email': user.email,
                'web_url': user.web_url
            }
            datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_base_user(df)

    def insert_t_base_group(self):
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for group in self.groups:
            data = {
                'created_at': now_str,
                'updated_at': now_str,
                'name': group.name,
                'git_id': group.id,
                'description': group.description,
                'web_url': group.web_url
            }
            datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_base_group(df)

    def insert_t_rel_project_user(self):
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.mysql.engine.connect() as con:
            df_user = pd.read_sql('select * from t_base_user', con=con)
            df_project = pd.read_sql('select * from t_base_project', con=con)

        for project in self.projects:
            project_idx = df_project[df_project['git_id'] == project.id].iloc[0]['id']
            headers = {'PRIVATE-TOKEN': self.token}
            response = requests.get(f'{self.base_url}/api/v4/projects/{str(project.id)}/members',
                                    headers=headers)
            for user in response.json():
                user_id = user['id']
                user_idx = df_user[df_user['git_id'] == user_id].iloc[0]['id']
                data = {
                    'created_at': now_str,
                    'updated_at': now_str,
                    'user_id': user_idx,
                    'project_id': project_idx,
                    'notice': 1,
                }
                datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_rel_project_user(df)

    def insert_t_rel_project_group(self):
        # 属于组的项目和属于个人的项目分别存在不同的两个关系表
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for project in self.projects:
            if project.namespace['kind'] != 'group':
                continue
            group_id = project.namespace['id']
            project_id = project.id
            data = {
                'created_at': now_str,
                'updated_at': now_str,
                'project_id': project_id,
                'group_id': group_id
            }
            datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_rel_project_group(df)

    def insert_t_rel_group_user(self):
        datas = []
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.mysql.engine.connect() as con:
            df_group = pd.read_sql('select * from t_base_group', con=con)
            df_user = pd.read_sql('select * from t_base_user', con=con)

        for i, row in df_group.iterrows():
            group_idx = row['id']
            group_id = row['git_id']

            headers = {'PRIVATE-TOKEN': self.token}
            response = requests.get(f'{self.base_url}/api/v4/groups/{str(group_id)}/members/all',
                                    headers=headers)
            for user in response.json():
                user_id = user['id']
                user_idx = df_user[df_user['git_id'] == user_id].iloc[0]['id']
                data = {
                    'created_at': now_str,
                    'updated_at': now_str,
                    'user_id': user_idx,
                    'group_id': group_idx
                }
                datas.append(data)
        df = pd.DataFrame(datas)
        self.mysql.insert_t_rel_group_user(df)

    def insert_t_log_project(self):
        self.mysql.insert_t_log_project(None)

    def insert_t_inspect_batch(self, project_id):
        """
        在审查一个项目之前，先查取这个项目的project_id, 向 t_inspect_batch 表插入一条数据
        """
        project = self.get_project_by_id(project_id)
        batch_id = self.mysql.insert_t_inspect_batch(project.id)
        return batch_id

    def insert_t_base_api(self):
        if not os.path.exists(self.api_path):
            print(f'{self.api_path} 不存在，跳过 insert_t_base_api')
            return
        df = pd.read_csv(self.api_path, encoding='gb18030', index_col=0)
        self.mysql.insert_t_base_api(df)

    def insert_t_base_database_url(self):
        if not os.path.exists(self.database_url_file_path):
            print(f'{self.database_url_file_path} 不存在，跳过 insert_t_base_database_url')
            return
        df = pd.read_csv(self.database_url_file_path, encoding='gb18030', index_col=0)
        self.mysql.insert_t_base_database_url(df)

    def check_project_latest_commit(self, project_id):
        """
        审查项目最新commit
        """
        project = self.get_project_by_id(project_id)
        commits = project.commits.list()
        if len(commits) == 0:
            raise NoCommitException(project.name)
        latest_commit_id = commits[0].id
        data = self.check_single_commit(project_id, latest_commit_id)
        return data

    def extract_database_url_from_all_project(self):
        for project in tqdm(self.projects):
            try:
                self.init_folder_path()
                print(f'extract_database_url from {project.name}...')
                project = self.get_project_by_id(project.id)
                commits = project.commits.list()
                if len(commits) == 0:
                    raise NoCommitException(project.name)
                latest_commit_id = commits[0].id

                zip_path = os.path.join(self.download_path, 'tmp.zip')
                dir_path = os.path.join(self.download_path, project.name)
                self.download_commit(project_id=project.id, commit_id=latest_commit_id, output_path=zip_path)
                self.unzip(zip_path, dir_path)

                extractor = Extractor(filepath=dir_path)
                df = extractor.extract_database_url()
                if len(df) > 0:
                    df['file'] = df['file'].apply(lambda x: x.replace(os.getcwd(), '').replace('//', '/'))
                    database_url_file = os.path.join(self.database_url_path, f'{project.name}.csv')

                    df['git_id'] = project.id
                    df.to_csv(database_url_file, encoding='gb18030', index=False)
            except NoCommitException as e:
                # 这里catch住没有commit的仓库，不报错，不入库
                print(e)
            except extractor.AstNodeException as e:
                # 这里catch住ast node出问题的仓库，不报错，不入库
                print(e)
            except extractor.FilePathException as e:
                # 路径问题
                print(e)
            except zipfile.BadZipFile as e:
                # 有些zip包是坏的
                print(e)
            except UnicodeDecodeError as e:
                # 文件编码问题
                print(e)
            except gitlab.exceptions.GitlabListError as e:
                # gitlab内部错误
                print(e)

        df_database_url = pd.DataFrame()
        for csv in glob(os.path.join(self.database_url_path, '*.csv')):
            print(csv)
            df = pd.read_csv(csv, encoding='gb18030')
            df_database_url = df_database_url.append(df)

        df_database_url.index = range(len(df_database_url))
        df_database_url.to_csv(self.database_url_file_path, encoding='gb18030')
        self.insert_t_base_database_url()

    def extract_api_from_all_project(self):
        for project in tqdm(self.projects):
            try:
                self.init_folder_path()
                print(f'extract_api from {project.name}...')
                project = self.get_project_by_id(project.id)
                commits = project.commits.list()
                if len(commits) == 0:
                    raise NoCommitException(project.name)
                latest_commit_id = commits[0].id

                zip_path = os.path.join(self.download_path, 'tmp.zip')
                dir_path = os.path.join(self.download_path, project.name)
                self.download_commit(project_id=project.id, commit_id=latest_commit_id, output_path=zip_path)
                self.unzip(zip_path, dir_path)

                extractor = Extractor(filepath=dir_path)
                df = extractor.extract_api()
                if len(df) > 0:
                    df['file'] = df['file'].apply(lambda x: x.replace(os.getcwd(), '').replace('//', '/'))
                    if extractor.project_type == 'frontend':
                        api_file = os.path.join(self.frontend_api_path, f'{project.name}.csv')
                    else:
                        api_file = os.path.join(self.backend_api_path, f'{project.name}.csv')
                    df['git_id'] = project.id
                    df.to_csv(api_file, encoding='gb18030', index=False)
            except NoCommitException as e:
                # 这里catch住没有commit的仓库，不报错，不入库
                print(e)
            except FilePathException as e:
                # 路径问题
                print(e)
            except zipfile.BadZipFile as e:
                # 有些zip包是坏的
                print(e)
            except UnicodeDecodeError as e:
                # 文件编码问题
                print(e)
            except gitlab.exceptions.GitlabListError as e:
                # gitlab内部错误
                print(e)

        df_back = pd.DataFrame()
        df_front = pd.DataFrame()
        for csv in glob(os.path.join(self.backend_api_path, '*.csv')):
            df = pd.read_csv(csv, encoding='gb18030')
            df_back = df_back.append(df)
        for csv in glob(os.path.join(self.frontend_api_path, '*.csv')):
            df = pd.read_csv(csv, encoding='gb18030')
            df_front = df_front.append(df)

        df_back.index = range(len(df_back))
        df_front.index = range(len(df_front))
        # df_front.to_csv('data/前端api.csv', encoding='gb18030')
        # df_back.to_csv('data/后端api.csv', encoding='gb18030')
        df_front['type'] = 'frontend'
        df_back['type'] = 'backend'
        df = df_front.append(df_back)
        df = df[['file', 'api', 'line', 'git_id', 'type']]
        df.to_csv(self.api_path, encoding='gb18030')

        self.insert_t_base_api()
