from mysql import Mysql
from gitlab_checker import GitLabChecker
import datetime
import time
from retrying import retry

def run():
    gitlabchecker = GitLabChecker()
    gitlabchecker.extract_api_from_all_project()
    gitlabchecker.extract_database_url_from_all_project()

if __name__ == '__main__':
    run()