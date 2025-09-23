"""
报告生成器 - 使用策略模式和工厂模式实现月报和changelog的生成

主要设计模式:
1. 策略模式: 不同类型报告使用不同的生成策略
2. 模板方法模式: 定义报告生成的基本流程
3. 工厂模式: 创建不同类型的报告生成器
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
import os
from qwen_agent.agents import Assistant
from dataclasses import dataclass
from enum import Enum


class PRType(Enum):
    """PR类型枚举"""
    FEATURE = "feature"
    BUGFIX = "bugfix"
    DOC = "doc"
    REFACTOR = "refactor"
    TEST = "test"


@dataclass
class PRInfo:
    """PR信息数据类"""
    number: int
    title: str
    html_url: str
    user: Dict[str, Any]
    highlight: str = ""
    function_value: str = ""
    score: int = 0
    pr_type: Optional[PRType] = None
    is_important: bool = False
    detailed_analysis: str = ""  # 用于存储重要PR的详细分析


class ReportGeneratorInterface(ABC):
    """报告生成器接口"""
    
    @abstractmethod
    def get_pr_list(self, **kwargs) -> List[PRInfo]:
        """获取PR列表 - 不同类型的报告有不同的获取方式"""
        pass
    
    @abstractmethod
    def analyze_prs_with_llm(self, pr_list: List[PRInfo]) -> List[PRInfo]:
        """使用LLM分析PR列表 - 通用逻辑"""
        pass
    
    @abstractmethod
    def generate_report(self, analyzed_prs: List[PRInfo]) -> str:
        """生成报告 - 不同类型的报告有不同的格式"""
        pass
    
    def create_report(self, **kwargs) -> str:
        self.owner = kwargs.get('owner', 'alibaba')
        self.repo = kwargs.get('repo', 'higress')

        """模板方法 - 定义报告生成的完整流程"""
        # 1. 获取PR列表
        pr_list = self.get_pr_list(**kwargs)
        
        # 2. 使用LLM分析PR
        analyzed_prs = self.analyze_prs_with_llm(pr_list)
        
        # 3. 生成报告
        report = self.generate_report(analyzed_prs)
        
        # 4. 保存报告到文件
        self.save_report_to_file(report, "report.md")
        
        # 5. 生成英文翻译
        if kwargs.get('translate', True):
            english_report = self.translate_to_english(report)
            self.save_report_to_file(english_report, "report.EN.md")
        
        return report
    
    def save_report_to_file(self, content: str, filename: str) -> None:
        """
        保存报告内容到文件
        
        Args:
            content: 报告内容
            filename: 文件名
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ 报告已保存到 {filename}")
        except Exception as e:
            print(f"❌ 保存文件 {filename} 失败: {str(e)}")
    
    def translate_to_english(self, content: str) -> str:
        """
        将报告内容翻译成英文
        
        Args:
            content: 中文报告内容
            
        Returns:
            英文翻译内容
        """
        print("🌐 开始翻译报告为英文...")
        
        translation_prompt = f"""
        请将以下中文报告翻译成英文，保持markdown格式不变，并确保技术术语翻译准确：

        {content}

        翻译要求：
        1. 保持所有markdown格式标记（#、##、###、-、[]()等）
        2. 保持所有链接和URL不变
        3. 技术术语使用准确的英文表达
        4. 保持专业的技术文档风格
        5. 不要添加任何额外的解释或注释
        """
        
        messages = [{'role': 'user', 'content': translation_prompt}]
        
        try:
            response_text = self._get_llm_response(messages)
            print("✅ 翻译完成")
            return response_text
        except Exception as e:
            print(f"❌ 翻译失败: {str(e)}")
            return f"# Translation Error\n\nFailed to translate the report: {str(e)}\n\n---\n\n{content}"


class BaseReportGenerator(ReportGeneratorInterface):
    """报告生成器基类 - 实现通用逻辑"""
    
    def __init__(self, sys_prompt: str = ""):
        self.sys_prompt = sys_prompt
        self.llm_assistant = self._create_llm_assistant()
        # 创建GitHub助手实例，避免重复创建
        from utils.pr_helper import GitHubHelper
        self.github_helper = GitHubHelper()
    
    def _create_llm_assistant(self) -> Assistant:
        """创建LLM助手"""
        llm_cfg = {
            'model': os.getenv('MODEL_NAME'),
            'model_server': os.getenv('MODEL_SERVER'),
            'api_key': os.getenv('DASHSCOPE_API_KEY'),
        }
        return Assistant(llm=llm_cfg)
    
    def analyze_prs_with_llm(self, pr_list: List[PRInfo]) -> List[PRInfo]:
        """使用LLM分析PR列表 - 通用实现"""
        analyzed_prs = []
        
        for pr in pr_list:
            try:
                # 调用LLM分析单个PR
                analyzed_pr = self._analyze_single_pr(pr)
                analyzed_prs.append(analyzed_pr)
            except Exception as e:
                print(f"分析PR #{pr.number}时发生错误: {str(e)}")
                analyzed_prs.append(pr)  # 如果分析失败，使用原始PR
        
        return analyzed_prs
    
    def _analyze_single_pr(self, pr: PRInfo) -> PRInfo:
        """分析单个PR - 子类可以重写此方法来定制分析逻辑"""
        # 默认实现：如果已经有分析结果就直接返回
        if pr.highlight and pr.function_value:
            return pr
        
        # 否则使用基础分析，子类需要提供prompt
        prompt = self._get_analysis_prompt()
        return self._basic_pr_analysis(pr, prompt)
    
    def _get_analysis_prompt(self) -> str:
        """获取分析prompt - 子类必须重写此方法"""
        raise NotImplementedError("子类必须实现 _get_analysis_prompt 方法")
    
    def _basic_pr_analysis(self, pr: PRInfo, analysis_prompt: str) -> PRInfo:
        """基础PR分析 - 调用MCP工具获取PR详细信息并分析"""
        try:
            # 1. 获取PR的详细信息和文件变更
            pr_details = self._get_pr_detailed_info(pr.number)
            if not pr_details:
                print(f"无法获取PR #{pr.number}的详细信息")
                return pr
            
            # 2. 准备分析数据
            pr_info = {
                "number": pr.number,
                "title": pr.title,
                "body": pr_details.get("body", "")[:500] if pr_details.get("body") else "",
                "total_changes": pr_details.get("total_changes", 0),
                "file_changes": pr_details.get("file_changes", []),
                "comments": pr_details.get("comments", [])
            }
            
            # 3. 准备评论摘要
            comments_summary = self._format_comments_for_analysis(pr_info["comments"])
            
            # 4. 构建完整的分析请求
            full_prompt = analysis_prompt.format(
                pr_number=pr.number,
                pr_title=pr.title,
                pr_body=pr_info["body"],
                total_changes=pr_info["total_changes"],
                file_changes=json.dumps(pr_info["file_changes"][:5], indent=2, ensure_ascii=False),  # 限制文件数量
                comments_summary=comments_summary
            )
            if self.sys_prompt:
                full_prompt = full_prompt + "\n\n下面是一些额外的要求，你也同样需要遵守：\n" + self.sys_prompt
            
            # 4. 使用LLM分析
            messages = [{'role': 'user', 'content': full_prompt}]
            response_text = self._get_llm_response(messages)
            # 去除首尾的 ```json 或 ```
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:]
            if response_text.strip().endswith("```"):
                response_text = response_text.strip()[:-3]
            response_text = response_text.strip()
            
            # 5. 解析结果
            result = json.loads(response_text)
            pr.highlight = result.get("highlight", pr.highlight)
            pr.function_value = result.get("function_value", pr.function_value)
            
            # 6. 如果包含评分，解析评分（月报专用）
            if "score" in result:
                try:
                    pr.score = int(result.get("score", 0))
                except (ValueError, TypeError):
                    pr.score = 0
            
            # 7. 如果是changelog，还要解析类型
            if hasattr(self, '_parse_pr_type') and "pr_type" in result:
                pr.pr_type = self._parse_pr_type(result.get("pr_type", "feature"))
            
            print(f"PR #{pr.number}分析完成")
            
        except Exception as e:
            print(f"LLM分析PR #{pr.number}失败: {str(e)}")
            # 设置默认值
            pr.highlight = pr.highlight or "技术更新"
            pr.function_value = pr.function_value or "功能改进"
        
        return pr
    
    def _get_pr_detailed_info(self, pr_number: int, owner: str = None, repo: str = None) -> dict:
        """获取PR的详细信息，包括文件变更和评论"""
        try:
            # 使用传入的参数或默认配置
            owner = owner or self.owner
            repo = repo or self.repo
            
            # 获取PR基本信息
            pr_info = self.github_helper.get_pull_request(
                owner=owner, 
                repo=repo, 
                pullNumber=pr_number
            )
            
            # 获取PR文件变更信息
            files_result = self.github_helper.get_pull_request_files(
                owner=owner, 
                repo=repo, 
                pullNumber=pr_number
            )
            
            # 获取PR评论信息
            comments_result = self._get_pr_comments(owner, repo, pr_number, self.github_helper)
            
            if not isinstance(files_result, list):
                return {
                    "body": pr_info.get("body", "") if pr_info else "",
                    "total_changes": 0,
                    "file_changes": [],
                    "comments": comments_result
                }
                
            # 计算总变更行数
            total_changes = 0
            for file_info in files_result:
                total_changes += file_info.get("additions", 0) + file_info.get("deletions", 0)
            
            # 准备文件变更信息
            file_changes = [
                {
                    "filename": file.get("filename", ""),
                    "additions": file.get("additions", 0),
                    "deletions": file.get("deletions", 0),
                    "patch": file.get("patch", "")[:200] if file.get("patch") else ""  # 截取部分patch内容
                } for file in files_result[:10]  # 限制文件数量
            ]
            
            return {
                "body": pr_info.get("body", "") if pr_info else "",
                "total_changes": total_changes,
                "file_changes": file_changes,
                "comments": comments_result
            }
            
        except Exception as e:
            print(f"获取PR #{pr_number}详细信息失败: {str(e)}")
            return {
                "body": "",
                "total_changes": 0,
                "file_changes": [],
                "comments": []
            }
    
    def _get_pr_comments(self, owner: str, repo: str, pr_number: int, github_helper) -> List[Dict[str, str]]:
        """获取PR评论信息"""
        try:
            # 调用MCP工具获取PR评论
            comments_data = github_helper.get_pull_request_comments(
                owner=owner,
                repo=repo,
                pullNumber=pr_number
            )
            
            if not isinstance(comments_data, list):
                return []
            
            # 提取评论的关键信息，限制评论数量和长度
            comments_summary = []
            for comment in comments_data:
                if isinstance(comment, dict) and comment.get("body"):
                    comment_info = {
                        "author": comment.get("user", {}).get("login", "unknown"),
                        "body": comment.get("body", "")[:300],  # 限制评论长度
                        "created_at": comment.get("created_at", "")
                    }
                    comments_summary.append(comment_info)
            
            return comments_summary
            
        except Exception as e:
            print(f"获取PR #{pr_number}评论失败: {str(e)}")
            return []
    
    def _format_comments_for_analysis(self, comments: List[Dict[str, str]]) -> str:
        """格式化评论信息用于AI分析"""
        if not comments:
            return "暂无评论"
        
        formatted_comments = []
        for i, comment in enumerate(comments):
            formatted_comment = f"评论{i} - {comment.get('author', 'unknown')}: {comment.get('body', '')}"
            formatted_comments.append(formatted_comment)
        
        return "\n".join(formatted_comments)
    
    def _create_pr_info(self, pr_data: Dict[str, Any], is_important: bool = False) -> PRInfo:
        """创建PRInfo对象的辅助方法"""
        return PRInfo(
            number=pr_data.get('number', 0),
            title=pr_data.get('title', ''),
            html_url=pr_data.get('html_url', ''),
            user=pr_data.get('user', {}),
            highlight='',  # 待LLM分析
            function_value='',  # 待LLM分析
            score=0,
            is_important=is_important
        )
    
    def _analyze_important_pr(self, pr: PRInfo) -> PRInfo:
        """分析重要PR - 获取详细信息（通用方法）"""
        # 首先进行基础分析
        pr = self._analyze_single_pr(pr)
        
        # 然后进行详细分析
        detailed_prompt = self._get_detailed_analysis_prompt()
        try:
            # 为重要PR获取更详细的信息，包括patch
            pr_details = self._get_important_pr_detailed_info(pr.number)
            if not pr_details:
                print(f"无法获取PR #{pr.number}的详细信息，跳过详细分析")
                return pr
                
            # 准备评论摘要
            comments_summary = self._format_comments_for_analysis(pr_details.get("comments", []))
            
            # 构建完整的详细分析请求
            full_prompt = detailed_prompt.format(
                pr_number=pr.number,
                pr_title=pr.title,
                pr_body=pr_details.get("body", "")[:1000],  # 增加长度用于详细分析
                total_changes=pr_details.get("total_changes", 0),
                file_changes=json.dumps(pr_details.get("file_changes", [])[:10], indent=2, ensure_ascii=False),
                patch_summary=pr_details.get("patch_summary", ""),
                comments_summary=comments_summary
            )
            if self.sys_prompt:
                full_prompt = full_prompt + "\n\n下面是一些额外的要求，你也同样需要遵守：\n" + self.sys_prompt
            
            # 使用LLM进行详细分析
            messages = [{'role': 'user', 'content': full_prompt}]
            response_text = self._get_llm_response(messages)
            # 去除首尾的 ```json 或 ```
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:]
            if response_text.strip().endswith("```"):
                response_text = response_text.strip()[:-3]
            response_text = response_text.strip()

            # 解析详细分析结果
            result = json.loads(response_text)
            
            # 构建详细分析内容
            detailed_sections = []
            
            if result.get("usage_background"):
                detailed_sections.append(f"**使用背景**\n\n{result['usage_background']}")
                
            if result.get("feature_details"):
                detailed_sections.append(f"**功能详述**\n\n{result['feature_details']}")
                
            if result.get("usage_guide"):
                detailed_sections.append(f"**使用方式**\n\n{result['usage_guide']}")
                
            if result.get("value_proposition"):
                detailed_sections.append(f"**功能价值**\n\n{result['value_proposition']}")
            
            pr.detailed_analysis = "\n\n".join(detailed_sections)
            print(f"重要PR #{pr.number}详细分析完成")
            
        except Exception as e:
            print(f"重要PR #{pr.number}详细分析失败: {str(e)}")
            pr.detailed_analysis = "详细分析暂时不可用，请参考基础信息。"
        
        return pr
    
    def _get_important_pr_detailed_info(self, pr_number: int) -> dict:
        """获取重要PR的详细信息，包括完整的patch内容（通用方法）"""
        try:
            # 获取基础信息
            pr_details = self._get_pr_detailed_info(pr_number)
            
            # 为重要PR获取更详细的文件变更信息，包括patch
            files_result = self.github_helper.get_pull_request_files(
                owner=self.owner,
                repo=self.repo,
                pullNumber=pr_number
            )
            
            if not isinstance(files_result, list):
                return pr_details
            
            # 构建详细的文件变更信息，包含完整patch
            enhanced_file_changes = []
            patch_summary_parts = []
            
            for file_info in files_result[:8]:  # 限制文件数量避免内容过长
                filename = file_info.get("filename", "")
                additions = file_info.get("additions", 0)
                deletions = file_info.get("deletions", 0)
                patch_content = file_info.get("patch", "")
                
                # 构建增强的文件信息
                enhanced_file = {
                    "filename": filename,
                    "additions": additions,
                    "deletions": deletions,
                    "status": file_info.get("status", "modified"),
                    "patch": patch_content[:2000] if patch_content else ""  # 保留更多patch内容
                }
                enhanced_file_changes.append(enhanced_file)
                
                # 构建patch摘要
                if patch_content:
                    # 提取关键的代码变更信息
                    patch_lines = patch_content.split('\n')
                    key_changes = []
                    
                    for line in patch_lines[:50]:  # 分析前50行patch
                        line = line.strip()
                        if line.startswith('+') and not line.startswith('+++'):
                            # 新增的代码行
                            if len(line) > 5 and not line.startswith('+ //') and not line.startswith('+ #'):
                                key_changes.append(f"新增: {line[1:].strip()[:100]}")
                        elif line.startswith('-') and not line.startswith('---'):
                            # 删除的代码行
                            if len(line) > 5 and not line.startswith('- //') and not line.startswith('- #'):
                                key_changes.append(f"删除: {line[1:].strip()[:100]}")
                    
                    if key_changes:
                        file_summary = f"文件 {filename} ({additions}+/{deletions}-):\n"
                        file_summary += "\n".join(key_changes[:5])  # 最多5个关键变更
                        patch_summary_parts.append(file_summary)
            
            # 更新详细信息
            pr_details["file_changes"] = enhanced_file_changes
            pr_details["patch_summary"] = "\n\n".join(patch_summary_parts[:5]) if patch_summary_parts else ""
            
            print(f"✅ 已获取重要PR #{pr_number}的增强详细信息（包含patch内容）")
            return pr_details
            
        except Exception as e:
            print(f"获取重要PR #{pr_number}详细信息失败: {str(e)}")
            # 降级到基础信息
            return self._get_pr_detailed_info(pr_number)
    
    def _get_detailed_analysis_prompt(self) -> str:
        """获取重要PR的详细分析prompt（通用方法，子类可重写）"""
        return """
        你是一个专业的技术文档撰写专家，请对以下重要PR进行深度分析，为技术报告撰写详细的功能介绍。

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
    
    def _get_llm_response(self, messages: List[Dict[str, str]]) -> str:
        """获取LLM响应"""
        collected_responses = []
        for response in self.llm_assistant.run(messages=messages):
            if isinstance(response, list) and len(response) > 0:
                for msg in response:
                    if msg.get('role') == 'assistant' and msg.get('content'):
                        collected_responses.append(msg.get('content', ""))
        
        return collected_responses[-1] if collected_responses else ""


class ReportGeneratorFactory:
    """报告生成器工厂类"""
    
    @staticmethod
    def create_generator(report_type: str, **kwargs) -> ReportGeneratorInterface:
        """创建指定类型的报告生成器"""
        if report_type.lower() == "monthly":
            from monthly_report_generator import MonthlyReportGenerator
            return MonthlyReportGenerator()
        elif report_type.lower() == "changelog":
            from changelog_generator import ChangelogReportGenerator
            return ChangelogReportGenerator(kwargs.get('sys_prompt', ""))
        else:
            raise ValueError(f"不支持的报告类型: {report_type}") 