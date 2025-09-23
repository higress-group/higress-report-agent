"""
Changelog生成器 - 实现changelog特有的PR获取和报告格式生成逻辑
"""

from typing import List, Dict, Any
from collections import defaultdict
from report_generator import BaseReportGenerator, PRInfo, PRType



class ChangelogReportGenerator(BaseReportGenerator):
    """Changelog生成器"""
    
    def __init__(self, sys_prompt: str = ""):
        super().__init__(sys_prompt=sys_prompt)
        self._setup_changelog_llm()
    
    def _setup_changelog_llm(self):
        """设置changelog专用的LLM系统指令"""
        changelog_system = """
        你是一个专业的PR分类和分析助手，负责分析GitHub PR并为changelog生成分类信息。

        请根据以下标准对PR进行分析：

        1. PR类型分类：
           - feature: 新功能、功能增强、新特性
           - bugfix: Bug修复、问题解决
           - doc: 文档更新、文档修复
           - refactor: 代码重构、性能优化、代码清理
           - test: 测试相关、CI/CD改进

        2. 分析要求：
           - 技术看点：关键技术实现方式和原理(50字以上，100字以内)
           - 功能价值：功能价值概要，对用户的影响(50字以上，100字以内)

        请严格按照以下JSON格式返回，不要添加任何解释、语言标记、代码块符号（如 ```json）：
        {
            "pr_type": "feature|bugfix|doc|refactor|test",
            "highlight": "关键技术实现方式和原理(50字以上，100字以内)",
            "function_value": "功能价值概要，对用户的影响(50字以上，100字以内)"
        }
        """
        
        self.changelog_llm = self._create_llm_assistant()
        self.changelog_llm.system_message = changelog_system
    
    def get_pr_list(self, **kwargs) -> List[PRInfo]:
        """获取changelog的PR列表 - 根据pr_num_list获取，支持重要PR标记"""
        pr_num_list = kwargs.get('pr_num_list', [])
        important_pr_list = kwargs.get('important_pr_list', [])
        owner = self.owner
        repo = self.repo
        
        if not pr_num_list:
            print("警告: 没有提供PR编号列表")
            return []
        
        # 确保重要PR列表中的PR也在普通PR列表中
        all_pr_numbers = list(set(pr_num_list + important_pr_list))
        print(f"开始获取{len(all_pr_numbers)}个PR的详细信息...")
        if important_pr_list:
            print(f"其中{len(important_pr_list)}个被标记为重要PR: {important_pr_list}")
        
        pr_list = []
        for pr_number in all_pr_numbers:
            try:
                # 调用get_pull_request MCP工具获取单个PR信息
                pr_data = self.github_helper.get_pull_request(
                    owner=owner,
                    repo=repo,
                    pullNumber=pr_number
                )
                
                if pr_data:
                    is_important = pr_number in important_pr_list
                    pr_info = self._create_pr_info(pr_data, is_important)
                    pr_list.append(pr_info)
                    status = "重要PR" if is_important else "普通PR"
                    print(f"✓ 成功获取{status} #{pr_number}: {pr_info.title}")
                else:
                    print(f"✗ 获取PR #{pr_number}失败")
                    
            except Exception as e:
                print(f"✗ 获取PR #{pr_number}时发生错误: {str(e)}")
                continue
        
        print(f"成功获取{len(pr_list)}个PR的详细信息")
        return pr_list
    
    def analyze_prs_with_llm(self, pr_list: List[PRInfo]) -> List[PRInfo]:
        """Changelog的LLM分析 - 支持重要PR的详细分析"""
        analyzed_prs = []
        
        print(f"开始分析{len(pr_list)}个PR...")
        important_prs = [pr for pr in pr_list if pr.is_important]
        normal_prs = [pr for pr in pr_list if not pr.is_important]
        
        if important_prs:
            print(f"其中{len(important_prs)}个重要PR需要详细分析...")
        
        for i, pr in enumerate(pr_list):
            try:
                pr_type = "重要PR" if pr.is_important else "普通PR"
                print(f"正在分析{pr_type} #{pr.number}: {pr.title} ({i+1}/{len(pr_list)})")
                
                if pr.is_important:
                    # 对重要PR进行详细分析
                    analyzed_pr = self._analyze_important_pr(pr)
                else:
                    # 对普通PR进行标准分析
                    analyzed_pr = self._analyze_single_pr(pr)
                
                analyzed_prs.append(analyzed_pr)
                    
            except Exception as e:
                print(f"分析PR #{pr.number}时发生错误: {str(e)}")
                pr.highlight = pr.highlight or "技术更新"
                pr.function_value = pr.function_value or "功能改进"
                if pr.is_important:
                    pr.detailed_analysis = "详细分析暂不可用"
                analyzed_prs.append(pr)
        
        print(f"分析完成，共处理{len(analyzed_prs)}个PR")
        return analyzed_prs
    


    def _get_analysis_prompt(self) -> str:
        """获取changelog专用的分析prompt"""
        return """
        你是一个专业的PR分类和分析助手，负责分析GitHub PR并为changelog生成分类信息。

        请根据以下标准对PR进行分析：

        1. PR类型分类：
           - feature: 新功能、功能增强、新特性（标题包含feat、add、support、implement、enhance等）
           - bugfix: Bug修复、问题解决（标题包含fix、resolve、correct、patch等）
           - doc: 文档更新、文档修复（标题包含doc、readme、documentation、guide等）
           - refactor: 代码重构、性能优化、代码清理（标题包含refactor、optimize、improve、clean等）
           - test: 测试相关、CI/CD改进（标题包含test、ci、cd、workflow等）

        2. 分析要求（需要更具文件改动，主要参考pr标题和pr描述进行具体分析）：
           - 技术看点：关键技术实现方式和原理(50字以上，100字以下)
           - 功能价值：功能价值概要，对用户的影响(50字以上，100字以下)

        请分析以下PR：
        PR编号: #{pr_number}
        PR标题: {pr_title}
        PR描述: {pr_body}
        总变更行数: {total_changes}
        文件变更详情:
        {file_changes}
        
        社区评论摘要:
        {comments_summary}

        请严格按照以下JSON格式返回，不要添加任何解释、语言标记、代码块符号（如 ```json）：
        {{
            "pr_type": "feature|bugfix|doc|refactor|test",
            "highlight": "pr做了哪些变更(50字以上，100字以下)",
            "function_value": "功能价值概要，对用户的影响(50字以上，100字以下)"
        }}
        """
    
    def _parse_pr_type(self, pr_type_str: str) -> PRType:
        """解析PR类型字符串为枚举"""
        type_mapping = {
            'feature': PRType.FEATURE,
            'bugfix': PRType.BUGFIX,
            'doc': PRType.DOC,
            'refactor': PRType.REFACTOR,
            'test': PRType.TEST
        }
        return type_mapping.get(pr_type_str.lower(), PRType.FEATURE)
    
    def generate_report(self, analyzed_prs: List[PRInfo]) -> str:
        """生成changelog格式的报告 - 支持重要PR的详细展示"""
        # 分离重要PR和普通PR
        important_prs = [pr for pr in analyzed_prs if pr.is_important]
        normal_prs = [pr for pr in analyzed_prs if not pr.is_important]
        
        # 生成报告
        report = "# Release Notes\n\n"
        
        # 1. 生成概览部分
        report += self._generate_overview_section(analyzed_prs)
        
        # 2. 如果有重要PR，生成重要功能详述部分
        if important_prs:
            report += self._generate_important_features_section(important_prs)
        
        # 3. 生成完整变更日志
        report += self._generate_changelog_section(normal_prs)
        
        # 4. 添加统计信息
        report += self._generate_statistics_section(analyzed_prs)
        
        return report
    
    def _generate_overview_section(self, analyzed_prs: List[PRInfo]) -> str:
        """生成概览部分"""
        grouped_prs = self._group_prs_by_type(analyzed_prs)
        
        overview = "## 📋 本次发布概览\n\n"
        overview += f"本次发布包含 **{len(analyzed_prs)}** 项更新，涵盖了功能增强、Bug修复、性能优化等多个方面。\n\n"
        
        # 按类型统计
        type_stats = []
        type_names = {
            PRType.FEATURE: "新功能",
            PRType.BUGFIX: "Bug修复", 
            PRType.REFACTOR: "重构优化",
            PRType.DOC: "文档更新",
            PRType.TEST: "测试改进"
        }
        
        for pr_type, name in type_names.items():
            count = len(grouped_prs.get(pr_type, []))
            if count > 0:
                type_stats.append(f"**{name}**: {count}项")
        
        if type_stats:
            overview += "### 更新内容分布\n\n"
            overview += "- " + "\n- ".join(type_stats) + "\n\n"
        
        # 重要更新提示
        important_prs = [pr for pr in analyzed_prs if pr.is_important]
        if important_prs:
            overview += f"### ⭐ 重点关注\n\n本次发布包含 **{len(important_prs)}** 项重要更新，建议重点关注：\n\n"
            for pr in important_prs:
                overview += f"- **{pr.title}** ([#{pr.number}]({pr.html_url})): {pr.function_value}\n"
            overview += "\n详细信息请查看下方重要功能详述部分。\n\n"
        
        overview += "---\n\n"
        return overview
    
    def _generate_important_features_section(self, important_prs: List[PRInfo]) -> str:
        """生成重要功能详述部分"""
        section = "## 🌟 重要功能详述\n\n"
        section += "以下是本次发布中的重要功能和改进的详细说明：\n\n"
        
        for i, pr in enumerate(important_prs, 1):
            contributor_login = pr.user.get('login', '未知')
            contributor_url = pr.user.get('html_url', '#')
            
            section += f"### {i}. {pr.title}\n\n"
            section += f"**相关PR**: [#{pr.number}]({pr.html_url}) | "
            section += f"**贡献者**: [@{contributor_login}]({contributor_url})\n\n"
            
            if pr.detailed_analysis:
                section += f"{pr.detailed_analysis}\n\n"
            else:
                # 如果没有详细分析，使用基础信息
                section += f"**Change Log**: {pr.highlight}\n\n"
                section += f"**Feature Value**: {pr.function_value}\n\n"
            
            section += "---\n\n"
        
        return section
    
    def _generate_changelog_section(self, normal_prs: List[PRInfo]) -> str:
        """生成完整变更日志部分"""
        if not normal_prs:
            return ""
            
        # 按类型分组普通PR
        grouped_prs = self._group_prs_by_type(normal_prs)
        
        section = "## 📝 完整变更日志\n\n"
        
        # 定义类型顺序和标题
        type_order = [
            (PRType.FEATURE, "### 🚀 新功能 (Features)"),
            (PRType.BUGFIX, "### 🐛 Bug修复 (Bug Fixes)"),
            (PRType.REFACTOR, "### ♻️ 重构优化 (Refactoring)"),
            (PRType.DOC, "### 📚 文档更新 (Documentation)"),
            (PRType.TEST, "### 🧪 测试改进 (Testing)")
        ]
        
        for pr_type, type_title in type_order:
            prs = grouped_prs.get(pr_type, [])
            if prs:
                section += f"{type_title}\n\n"
                
                for pr in prs:
                    contributor_login = pr.user.get('login', '未知')
                    
                    section += f"- **Related PR**: [#{pr.number}]({pr.html_url}) \\\n"
                    section += f"  **Contributor**: @{contributor_login} \\\n"
                    section += f"  **Change Log**: {pr.highlight} \\\n"
                    section += f"  **Feature Value**: {pr.function_value}\n\n"
        
        return section
    
    def _generate_statistics_section(self, analyzed_prs: List[PRInfo]) -> str:
        """生成统计信息部分"""
        grouped_prs = self._group_prs_by_type(analyzed_prs)
        
        section = "---\n\n## 📊 发布统计\n\n"
        
        # 按类型统计
        type_order = [
            (PRType.FEATURE, "🚀 新功能"),
            (PRType.BUGFIX, "🐛 Bug修复"),
            (PRType.REFACTOR, "♻️ 重构优化"),
            (PRType.DOC, "📚 文档更新"),
            (PRType.TEST, "🧪 测试改进")
        ]
        
        for pr_type, type_name in type_order:
            count = len(grouped_prs.get(pr_type, []))
            if count > 0:
                section += f"- {type_name}: {count}项\n"
        
        total_count = len(analyzed_prs)
        important_count = len([pr for pr in analyzed_prs if pr.is_important])
        
        section += f"\n**总计**: {total_count}项更改"
        if important_count > 0:
            section += f"（包含{important_count}项重要更新）"
        section += "\n\n"
        
        section += "感谢所有贡献者的辛勤付出！🎉\n"
        
        return section
    
    def _group_prs_by_type(self, prs: List[PRInfo]) -> Dict[PRType, List[PRInfo]]:
        """按类型分组PR"""
        grouped = defaultdict(list)
        
        for pr in prs:
            pr_type = pr.pr_type or PRType.FEATURE
            grouped[pr_type].append(pr)
        
        # 对每个类型内的PR按编号排序
        for pr_type in grouped:
            grouped[pr_type].sort(key=lambda x: x.number, reverse=True)
        
        return dict(grouped)
    
    def _get_detailed_analysis_prompt(self) -> str:
        """获取重要PR的详细分析prompt（changelog专用版本）"""
        return """
        你是一个专业的技术文档撰写专家，请对以下重要PR进行深度分析，为changelog撰写详细的功能介绍。

        你将获得完整的代码变更信息（包括patch内容）和社区评论，请基于这些具体信息进行权威分析。

        请从以下几个维度进行详细分析：

        1. **使用背景**: 
           - 解决了什么问题或满足了什么需求
           - 为什么需要这个功能/修复
           - 目标用户群体

        2. **功能详述**:
           - 具体实现了什么功能
           - 核心技术要点和创新之处
           - 与现有功能的关系和差异
           - 基于代码变更的技术分析

        3. **使用方式**:
           - 如何启用和配置这个功能
           - 典型的使用场景和示例
           - 注意事项和最佳实践

        4. **功能价值**:
           - 为用户带来的具体好处
           - 对系统性能、稳定性、易用性的提升
           - 在生态中的重要性

        请分析以下重要PR：
        PR编号: #{pr_number}
        PR标题: {pr_title}
        PR描述: {pr_body}
        总变更行数: {total_changes}
        
        主要文件变更:
        {file_changes}
        
        关键代码变更摘要:
        {patch_summary}
        
        社区评论摘要:
        {comments_summary}

        请基于具体的代码变更内容和社区反馈进行分析，严格按照以下JSON格式返回（每个字段200-400字）：
        {{
            "pr_type": "feature|bugfix|doc|refactor|test",
            "highlight": "功能概要描述(50字以上，100字以下)",
            "function_value": "功能价值简述(50字以上，100字以下)",
            "usage_background": "使用背景详述(200-400字)",
            "feature_details": "功能详述，包含技术实现分析(200-400字)", 
            "usage_guide": "使用方式详述(200-400字)",
            "value_proposition": "功能价值详述(200-400字)"
        }}
        """ 