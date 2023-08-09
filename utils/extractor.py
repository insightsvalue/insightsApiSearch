import os
import re
import pandas as pd


class FilePathException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return (self.msg)


class Extractor():
    def __init__(self, filepath):
        if not os.path.exists(filepath):
            raise FilePathException(f'{filepath} 路径不存在')

        if os.path.isdir(filepath):
            """
            module和单个文件的情况分开处理,如果某包含py文件的文件夹下没有__init__.py文件，
            pylint会报错 [Errno 2] No such file or directory: './__init__.py' (parse-error)
            因此给这样的文件夹新建__init__.py文件
            """
            self.module_path = filepath
            # self.init_folder(self.module_path)
            # self.filepaths = []
            # for root, dirs, files in os.walk(self.module_path, topdown=False):
            #     for file in files:
            #         if os.path.splitext(file)[1] == '.py':
            #             self.filepaths.append(os.path.join(root, file))

        else:
            raise FilePathException(f'f{filepath}不符合要求，要求文件夹!')

    # def init_folder(self, path):
    #     """第一层 __init__.py必加"""
    #     init_file = os.path.join(path, '__init__.py')
    #     if not os.path.exists(init_file):
    #         with open(os.path.join(path, '__init__.py'), 'a') as f:
    #             f.write('')
    #     for root, dirs, files in os.walk(path, topdown=False):
    #         for file in files:
    #             if os.path.splitext(file)[1] == '.py':
    #                 init_file = os.path.join(root, '__init__.py')
    #                 if not os.path.exists(init_file):
    #                     with open(os.path.join(root, '__init__.py'), 'a') as f:
    #                         f.write('')
    #                     break

    @property
    def project_type(self):
        """
        判断项目属于前端还是api-framework或者yard-base
        :return:
        """
        all_files = []
        all_dirs = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            all_files.extend(files)
            all_dirs.extend(dirs)
        if 'package.json' in all_files:
            return 'frontend'
        elif 'runserver.py' in all_files:
            if 'bin' in all_dirs:
                return 'yard-base'
            else:
                return 'api-framework'
        else:
            return 'other'

    def check_f_string(self, text):
        if 'f"' in text or "f'" in text:
            if '{' in text and '}' in text:
                return True
            if '}' in text and '{' in text:
                return True
        return False

    def check_comment(self, text):
        text = text.replace(' ', '')
        if len(text) == 0:
            return False
        if text[0] == '#':
            return True
        return False

    def recover_f_string(self, f_string, lines):
        var_reg = '(?<={).+?(?=\})'
        var_names = re.findall(var_reg, f_string)
        var_dict = {}
        for var_name in var_names:
            for line in lines:
                if f_string == line:
                    break
                line = line.replace(' ', '')
                reg = f'(?<={var_name}\=[\'\"]).+?(?=[\'\"])'
                var_value = re.findall(reg, line)
                if len(var_value) != 0:
                    var_dict[var_name] = var_value[0]
        for var_name in var_dict.keys():
            f_string = f_string.replace('{' + f'{var_name}' + '}', var_dict[var_name])
        return f_string.replace(' ', '')

    def extract_database_url(self):
        datas = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            for file in files:
                if os.path.splitext(file)[1] == '.py':
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r') as f:
                        lines = f.readlines()
                        for idx, line in enumerate(lines):
                            database_url = self.extract_database_url_from_line(line, lines)
                            if database_url == None:
                                continue
                            data = {'file': os.path.abspath(filepath).replace(self.module_path, ''),
                                 'database_url': database_url.replace(re.search('(?<=\/\/).+?(?=\@)', database_url).group(), '账号密码已打码'), # 这里加密一下密码字段
                                 'line': idx + 1, 'text': line}
                            datas.append(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_database_url_from_line(self, text, lines):
        # 需要解决这种情况：mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8
        # reg = '(?<=[\"\'`]).+\+.+:\/\/.+\:.+@.+\/.+(?=[\"\'`])'
        if self.check_comment(text) == True:
            return None

        reg = '(?<=[\"\'])[^\"\']+\+.+:\/\/.+\:.+@.+\/.+(?=[\"\'`])'
        result = re.search(reg, text)

        if result == None:
            return None
        else:
            database_url = result.group()
        if self.check_f_string(text) == True:
            try:
                database_url = self.recover_f_string(text, lines)
                return re.search(reg, database_url).group()
            except:
                pass
        return database_url

    def extract_api(self):
        if self.project_type == 'yard-base':
            df = self.extract_api_from_yard_base()
        elif self.project_type == 'api-framework':
            df = self.extract_api_from_api_framework()
        elif self.project_type == 'frontend':
            df = self.extract_api_from_frontend()
        else:
            df = pd.DataFrame()
        return df

    def extract_api_from_line(self, text):
        reg_with_port = '(?<=[\"\'`])[http|https].+/.+:[0-9]+.+(?=[\"\'`])'
        apis_with_port = re.findall(reg_with_port, text)

        # reg = '(?<=[\"\'])/.+/.+(?=[\"\'])'
        # reg = '/.+/.+(?=[\"\'`])'
        reg = '(?<=[\"\'`])/.*?(?=[\"\'`])'
        apis_without_port = re.findall(reg, text)

        apis = set(apis_with_port + apis_without_port)
        apis = [api for api in apis if ' ' not in api or '<' not in api or '(' not in api]
        apis = [api.split('?')[0] for api in apis if len(api) < 100 and len(api) > 4] # ?后的参数要去除
        return apis

    def extract_api_from_yard_base(self):
        def get_default_url_name(cls_name):
            p = re.compile(r'([a-z]|\d)([A-Z])')
            return re.sub(p, r'\1-\2', cls_name).lower().replace('.py', '')

        def get_class_name(file):
            class_names = []
            if file.endswith('.py'):
                with open(file, 'r') as f:
                    try:
                        lines = f.readlines()
                        for line in lines:
                            if 'class' in line and 'AbstractApi' in line and '(' in line and ')' in line:
                                class_name = line.split('class')[1].split('(')[0].replace(' ', '')
                                class_names.append(class_name)
                        return class_names
                    except UnicodeDecodeError:
                        return []
            return []

        datas = []
        app_path = os.path.join(self.module_path, 'src', 'app')
        for dir_path, dir_names, files in os.walk(app_path):
            for file in files:
                if '__pycache__' in dir_path:
                    continue
                file_full_path = os.path.join(dir_path, file)
                class_names = get_class_name(file_full_path)
                if len(class_names) == 0:
                    continue
                for class_name in class_names:
                    file_path = os.path.join(dir_path.replace(app_path, ''), file)
                    path1, path2 = os.path.split(file_path)
                    if path1 == '' or path1[0] != '/':
                        path1 = '/' + path1

                    url = os.path.join(path1, get_default_url_name(class_name))
                    # url = '/'.join([get_default_url_name(item) for item in file_path.split('/')])
                    datas.append({
                        'file': file_full_path.replace(self.module_path, ''),
                        'api': url,
                        'line': '-'})
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_api_from_api_framework(self):
        datas = []
        for dir_path, dir_names, files in os.walk(self.module_path):
            for file in files:
                single_file_urls = []
                if file == '__init__.py':
                    with open(os.path.join(dir_path, file), 'r') as f:
                        try:
                            lines = f.readlines()
                            for line in lines:
                                if self.check_comment(line) == True:
                                    continue
                                if 'Blueprint(' in line:
                                    reg = '(?<=[\"\'`]).+?(?=[\"\'`])'
                                    Blueprint_name = re.findall(reg, line)[0]
                                if 'add_resource(' in line:
                                    reg = '(?<=[\"\'`]).+(?=[\"\'`])'
                                    url = re.findall(reg, line)
                                    single_file_urls.extend(url)
                        except UnicodeDecodeError:
                            continue
                if len(single_file_urls) > 0:
                    single_file_urls = ['/' + Blueprint_name + url for url in single_file_urls]
                    data = [{'file': os.path.abspath(os.path.join(dir_path, file)).replace(self.module_path, ''),
                             'api': api,
                             'line': '-'} for api in single_file_urls]
                    datas.extend(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df

    def extract_api_from_frontend(self):
        datas = []
        for root, dirs, files in os.walk(self.module_path, topdown=False):
            if os.path.join(self.module_path, 'node_modules') in root:
                continue
            for file in files:
                if os.path.splitext(file)[1] in ['.js', '.ts', '.tsx']:
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r') as f:
                        lines = f.readlines()
                        for idx, line in enumerate(lines):
                            if 'from' in line or 'import' in line:
                                continue
                            apis = self.extract_api_from_line(line)
                            data = [{'file': os.path.abspath(filepath).replace(self.module_path, ''), 'api': api,
                                     'line': idx + 1} for api in apis]
                            datas.extend(data)
        df = pd.DataFrame(datas)
        df.index = [i for i in range(len(df))]
        return df


"""
由于使用多进程的原因
程序需要在
if __name__ == '__main__':
下执行
"""
