import argparse
from datetime import datetime, timezone


class AgentConfig:
    """Agent配置类，支持命令行参数和交互模式"""

    # 运行模式常量
    MODE_INTERACTIVE = 1
    MODE_ARGS = 2

    # 报告类型常量
    REPORT_MONTHLY = 1
    REPORT_CHANGELOG = 2
    EXIT = 3

    def __init__(self):
        # 基础配置
        self.mode = self.MODE_INTERACTIVE

        # 报告类型选择
        self.choice = AgentConfig.REPORT_MONTHLY

        # 月报参数
        self.month = datetime.now(timezone.utc).month
        self.year = datetime.now(timezone.utc).year

        # Changelog参数
        self.pr_num_list = []

        # 通用参数
        self.important_pr_list = []
        self.translate = True
        self.sys_prompt = ""

    @classmethod
    def from_args(cls) -> 'AgentConfig':
        """从命令行参数构建配置"""
        parser = argparse.ArgumentParser(description='github报告生成工具')

        # 基本参数
        parser.add_argument('--mode', type=int, choices=[cls.MODE_INTERACTIVE, cls.MODE_ARGS],
                            default=cls.MODE_INTERACTIVE,
                            help='运行模式: 1=交互模式, 2=命令行参数模式，默认1')

        # 报告类型
        parser.add_argument('--choice', type=int, choices=[cls.REPORT_MONTHLY, cls.REPORT_CHANGELOG],
                            help='报告类型: 1=月报, 2=Changelog，默认1')

        # 月报相关参数
        parser.add_argument('--month', type=int, help='月份 (仅月报有效，默认当前月份)')
        parser.add_argument('--year', type=int, help='年份 (仅月报有效，默认当前年份)')

        # Changelog相关参数
        parser.add_argument('--pr_nums', type=str,
                            help='PR编号列表，逗号分隔 (仅Changelog有效)')

        # 通用参数
        parser.add_argument('--important_prs', type=str,
                            help='重要PR编号列表，逗号分隔')
        parser.add_argument('--no_translate', action='store_true',
                            help='设置此标志将不生成英文翻译')
        parser.add_argument('--sys_prompt_file', type=str, default='',
                            help='自定义系统提示词文件路径')

        args = parser.parse_args()
        config = cls()

        if args.mode:
            config.mode = args.mode
        if args.choice:
            config.choice = args.choice

        # 设置月报参数
        if args.month:
            config.month = args.month
        if args.year:
            config.year = args.year

        # 设置Changelog参数
        if args.pr_nums:
            try:
                config.pr_num_list = [int(x.strip())
                                      for x in args.pr_nums.split(',')]
            except ValueError:
                raise ValueError("PR编号格式不正确，请输入数字")

        # 设置通用参数
        if args.important_prs:
            try:
                config.important_pr_list = [
                    int(x.strip()) for x in args.important_prs.split(',')]
            except ValueError:
                print("重要PR编号格式不正确，将忽略重要PR设置")
                config.important_pr_list = []

        config.translate = not args.no_translate

        if args.sys_prompt_file:
            try:
                with open(args.sys_prompt_file, 'r', encoding='utf-8') as f:
                    config.sys_prompt = f.read()
            except Exception as e:
                print(
                    f"无法读取系统提示词文件 {args.sys_prompt_file}，将使用默认提示词。错误: {e}")
                config.sys_prompt = ""

        config.validate()
        return config

    def validate(self) -> bool:
        """验证配置是否合法"""
        if self.mode != self.MODE_ARGS:
            return True

        # 如果是命令行参数模式，需要检查必要的参数
        if self.choice == self.REPORT_CHANGELOG:
            if not self.pr_num_list:
                raise ValueError("生成Changelog时必须提供PR编号列表 (--pr_nums)")

        return True
