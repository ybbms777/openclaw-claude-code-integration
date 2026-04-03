#!/usr/local/bin/python3.12
"""
bash_ast.py — Bash AST 解析安全层

参考 Claude Code 源码四层安全机制中的 AST 解析层设计，
用纯 Python 实现，用于命令安全检测。

功能：
1. Bash 命令词法分析（tokenizer）
2. Bash AST 递归下降解析
3. 危险命令节点识别：rm, mv, dd, chmod, curl|wget+pipeline
4. 路径遍历检测：../ 过多、~/.ssh/、/etc/ 等敏感路径
5. 注入检测：; && || | 后的危险命令

用法：
  python3 bash_ast.py '<command>'
  echo $?  # 0=SAFE, 1=PARSE_FAILED, 2=UNSAFE

返回结构：
  {
    "threat": 0|1|2,
    "level": "CLEAR"|"PARSE_FAILED"|"UNSAFE",
    "reason": str,
    "detail": str,
    "ast": dict | None
  }
"""

import re
import sys
import json
from enum import IntEnum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ─── 威胁等级 ───────────────────────────────────────────────────────────────

class Threat(IntEnum):
    SAFE = 0
    PARSE_FAILED = 1
    UNSAFE = 2


# ─── Token 定义 ─────────────────────────────────────────────────────────────

class TokenType(IntEnum):
    WORD = 0          # 普通单词
    PIPE = 1          # |
    AMPERSAND = 2     # &
    SEMICOLON = 3     # ;
    AND = 4           # &&
    OR = 5            # ||
    REDIR_IN = 6      # <
    REDIR_OUT = 7     # >
    REDIR_APPEND = 8  # >>
    REDIR_ERR = 9     # 2>
    COMMAND_SUB = 10  # $()
    BACKTICK = 11     # `
    VAR = 12         # $VAR
    VAR_BRACE = 13   # ${VAR}
    COMMENT = 14     # #
    NEWLINE = 15
    EOF = 16
    LPAREN = 17
    RPAREN = 18


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int


# ─── AST 节点定义 ───────────────────────────────────────────────────────────

class NodeType(IntEnum):
    PROGRAM = 0
    COMMAND_CHAIN = 1
    PIPELINE = 2
    COMMAND = 3
    ARG = 4
    REDIRECTION = 5
    ASSIGNMENT = 6
    WORD = 7  # 单词 token（命令替换、变量等特殊词）


@dataclass
class ASTNode:
    type: NodeType
    value: str = ""
    children: List['ASTNode'] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "type": NodeType(self.type).name,
            "value": self.value,
            "children": [c.to_dict() for c in self.children],
            "meta": self.meta,
        }


# ─── 词法分析器 ─────────────────────────────────────────────────────────────

class Lexer:
    """Bash 命令词法分析器"""

    def __init__(self, command: str):
        self.command = command
        self.pos = 0
        self.len = len(command)

    def _peek(self, offset: int = 0) -> Optional[str]:
        idx = self.pos + offset
        if idx >= self.len:
            return None
        return self.command[idx]

    def _advance(self, n: int = 1) -> str:
        ch = self.command[self.pos] if self.pos < self.len else ""
        self.pos += n
        return ch

    def _skip_whitespace(self):
        while self.pos < self.len and self.command[self.pos] in " \t":
            self.pos += 1

    def _read_quoted(self, quote: str) -> str:
        """读取引号包围的内容"""
        self._advance()  # 跳过开头引号
        result = ""
        while self.pos < self.len:
            ch = self.command[self.pos]
            if ch == quote:
                self._advance()
                return result
            if ch == '\\' and self.pos + 1 < self.len:
                self._advance()  # skip \
                result += self._advance()
            else:
                result += self._advance()
        return result  # 未闭合，返回已有内容

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.pos < self.len:
            self._skip_whitespace()
            if self.pos >= self.len:
                break

            ch = self.command[self.pos]

            # 注释
            if ch == '#':
                tokens.append(Token(TokenType.COMMENT, self.command[self.pos:], self.pos))
                break

            # 换行符
            if ch == '\n':
                tokens.append(Token(TokenType.NEWLINE, ch, self.pos))
                self._advance()
                continue

            # 命令替换 $()
            if ch == '$' and self._peek(1) == '(':
                start = self.pos
                depth = 0
                self._advance(2)  # 跳过 $(
                result = "$("
                while self.pos < self.len:
                    cc = self.command[self.pos]
                    if cc == '(':
                        depth += 1
                        result += cc
                        self._advance()
                    elif cc == ')' and depth > 0:
                        depth -= 1
                        result += cc
                        self._advance()
                    elif cc == ')' and depth == 0:
                        result += cc
                        self._advance()
                        break
                    else:
                        result += cc
                        self._advance()
                tokens.append(Token(TokenType.COMMAND_SUB, result, start))
                continue

            # 反引号
            if ch == '`':
                start = self.pos
                self._advance()
                result = "`"
                while self.pos < self.len and self.command[self.pos] != '`':
                    if self.command[self.pos] == '\\':
                        result += self._advance()
                    result += self._advance()
                if self.pos < self.len:
                    result += self._advance()
                tokens.append(Token(TokenType.BACKTICK, result, start))
                continue

            # 变量 ${var}
            if ch == '$' and self._peek(1) == '{':
                start = self.pos
                self._advance(2)
                result = "${"
                while self.pos < self.len and self.command[self.pos] != '}':
                    result += self._advance()
                if self.pos < self.len:
                    result += self._advance()
                tokens.append(Token(TokenType.VAR_BRACE, result, start))
                continue

            # 变量 $var
            if ch == '$' and self._peek(1) is not None and self._peek(1) not in " \t\n;&|&><":
                start = self.pos
                self._advance()
                var_name = ""
                while self.pos < self.len and self.command[self.pos] not in " \t\n;&|&><":
                    var_name += self._advance()
                tokens.append(Token(TokenType.VAR, f"${var_name}", start))
                continue

            # 双引号字符串
            if ch == '"':
                val = self._read_quoted('"')
                tokens.append(Token(TokenType.WORD, f'"{val}"', self.pos - len(val) - 2))
                continue

            # 单引号字符串
            if ch == "'":
                val = self._read_quoted("'")
                tokens.append(Token(TokenType.WORD, f"'{val}'", self.pos - len(val) - 2))
                continue

            # 操作符
            if ch == '|':
                if self._peek(1) == '|':
                    tokens.append(Token(TokenType.OR, "||", self.pos))
                    self._advance(2)
                else:
                    tokens.append(Token(TokenType.PIPE, "|", self.pos))
                    self._advance()
                continue

            if ch == '&':
                if self._peek(1) == '&':
                    tokens.append(Token(TokenType.AND, "&&", self.pos))
                    self._advance(2)
                else:
                    tokens.append(Token(TokenType.AMPERSAND, "&", self.pos))
                    self._advance()
                continue

            if ch == ';':
                tokens.append(Token(TokenType.SEMICOLON, ";", self.pos))
                self._advance()
                continue

            if ch == '<':
                tokens.append(Token(TokenType.REDIR_IN, "<", self.pos))
                self._advance()
                continue

            if ch == '>':
                if self._peek(1) == '>':
                    tokens.append(Token(TokenType.REDIR_APPEND, ">>", self.pos))
                    self._advance(2)
                else:
                    tokens.append(Token(TokenType.REDIR_OUT, ">", self.pos))
                    self._advance()
                continue

            if ch == '(':
                tokens.append(Token(TokenType.LPAREN, "(", self.pos))
                self._advance()
                continue

            if ch == ')':
                tokens.append(Token(TokenType.RPAREN, ")", self.pos))
                self._advance()
                continue

            # 普通单词
            start = self.pos
            word = ""
            while self.pos < self.len:
                cc = self.command[self.pos]
                if cc in " \t\n;&|&><()":
                    break
                word += self._advance()
            if word:
                tokens.append(Token(TokenType.WORD, word, start))

        tokens.append(Token(TokenType.EOF, "", self.pos))
        return tokens


# ─── AST 解析器 ─────────────────────────────────────────────────────────────

class Parser:
    """Bash AST 递归下降解析器"""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        t = self._peek()
        self.pos += 1
        return t

    def _is(self, type_: TokenType) -> bool:
        return self._peek().type == type_

    def _match(self, *types: TokenType) -> bool:
        if self._peek().type in types:
            return True
        return False

    def parse(self) -> ASTNode:
        """解析整个程序：命令链"""
        node = ASTNode(NodeType.PROGRAM)
        while not self._is(TokenType.EOF):
            # 跳过换行符
            if self._is(TokenType.NEWLINE):
                self._advance()
                continue
            # 解析单个 pipeline
            cmd_node = self._parse_pipeline()
            if cmd_node:
                node.children.append(cmd_node)
            # 检查分隔符
            if self._is(TokenType.SEMICOLON):
                self._advance()
            elif self._is(TokenType.AND):
                and_token = self._advance()
                # && 分隔的命令链
                right = self._parse_pipeline()
                if right:
                    chain = ASTNode(NodeType.COMMAND_CHAIN, value="&&")
                    chain.children = [cmd_node, right]
                    node.children[-1] = chain
            elif self._is(TokenType.OR):
                or_token = self._advance()
                right = self._parse_pipeline()
                if right:
                    chain = ASTNode(NodeType.COMMAND_CHAIN, value="||")
                    chain.children = [cmd_node, right]
                    node.children[-1] = chain
            elif self._is(TokenType.AMPERSAND):
                self._advance()
            else:
                break
        return node

    def _parse_pipeline(self) -> Optional[ASTNode]:
        """解析 pipeline（用 | 分隔的命令序列）"""
        first = self._parse_command()
        if not first:
            return None

        if self._is(TokenType.PIPE):
            pipe_node = ASTNode(NodeType.PIPELINE, value="|")
            pipe_node.children.append(first)
            while self._is(TokenType.PIPE):
                self._advance()
                next_cmd = self._parse_command()
                if next_cmd:
                    pipe_node.children.append(next_cmd)
            return pipe_node
        return first

    def _parse_command(self) -> Optional[ASTNode]:
        """解析单个命令"""
        node = ASTNode(NodeType.COMMAND)
        while True:
            if self._is(TokenType.EOF) or self._is(TokenType.NEWLINE):
                break
            if self._is(TokenType.SEMICOLON) or self._is(TokenType.AND) or \
               self._is(TokenType.OR) or self._is(TokenType.PIPE):
                break
            if self._is(TokenType.REDIR_IN) or self._is(TokenType.REDIR_OUT) or \
               self._is(TokenType.REDIR_APPEND) or self._is(TokenType.REDIR_ERR):
                redir = self._parse_redirection()
                if redir:
                    node.children.append(redir)
                continue
            if self._is(TokenType.LPAREN):
                self._advance()
                sub = self._parse_command()
                if self._is(TokenType.RPAREN):
                    self._advance()
                node.meta['has_subshell'] = True
                node.children.append(sub or ASTNode(NodeType.WORD, value="()"))
                continue

            # 跳过命令替换和反引号（已经是危险标记）
            if self._is(TokenType.COMMAND_SUB) or self._is(TokenType.BACKTICK):
                t = self._advance()
                node.children.append(ASTNode(NodeType.WORD, value=t.value, meta={"dangerous": True, "reason": "command_substitution"}))
                continue

            # 变量扩展
            if self._is(TokenType.VAR) or self._is(TokenType.VAR_BRACE):
                t = self._advance()
                node.children.append(ASTNode(NodeType.WORD, value=t.value, meta={"has_variable": True}))
                continue

            if self._is(TokenType.WORD):
                t = self._advance()
                node.children.append(ASTNode(NodeType.ARG, value=t.value))
            else:
                self._advance()  # 跳过未知 token

        return node


# ─── 安全分析器 ─────────────────────────────────────────────────────────────

class BashASTAnalyzer:
    """
    Bash AST 安全分析器

    Claude Code 四层安全机制第一层：AST 解析层
    - 危险命令识别
    - 路径遍历检测
    - 注入攻击检测
    """

    # 高危命令黑名单
    DANGEROUS_COMMANDS = {
        "rm", "rmdir", "del", "unlink",
        "mv", "move",
        "dd",
        "chmod", "chown", "chgrp",
        "curl", "wget", "nc", "netcat",
        "bash", "sh", "zsh", "csh",
        "python", "python2", "python3", "ruby", "perl", "node", "npm",
        "eval", "exec",
        "source", ".",
        "mkfs", "fdisk", "parted",
        "shutdown", "reboot", "halt", "poweroff",
        "iptables", "ufw", "firewalld",
        "ssh", "scp", "sftp",
        "mount", "umount",
        "kill", "killall", "pkill",
    }

    # 危险命令后跟管道 shell 的模式
    PIPE_TO_SHELL_PATTERNS = [
        (r'curl', r'\|.*(bash|sh|zsh|perl|python|ruby)'),
        (r'wget', r'\|.*(bash|sh|zsh|perl|python|ruby)'),
        (r'nc', r'\|.*(bash|sh|zsh)'),
        (r'netcat', r'\|.*(bash|sh|zsh)'),
    ]

    # 敏感路径模式
    SENSITIVE_PATHS = [
        (r'/\.ssh/', "SSH 配置目录 (~/.ssh/)"),
        (r'/\.aws/', "AWS 配置目录 (~/.aws/)"),
        (r'/\.kube/', "K8s 配置目录 (~/.kube/)"),
        (r'/\.git/', "Git 仓库目录"),
        (r'/etc/', "系统配置目录 (/etc/)"),
        (r'/\.ssh', "SSH 配置路径"),
        (r'/root/', "Root 主目录"),
        (r'/proc/', "Linux proc 文件系统"),
        (r'/sys/', "Linux sys 文件系统"),
        (r'/dev/', "设备文件目录 (仅 /dev/null 等正常用法除外)"),
        (r'/boot/', "启动目录"),
        (r'/var/log/', "日志目录"),
        (r'/etc/passwd', "用户密码文件"),
        (r'/etc/shadow', "用户影子密码文件"),
        (r'/etc/sudoers', "Sudo 配置文件"),
    ]

    # 递归路径遍历（ ../ 过多）
    PATH_TRAVERSAL_PATTERN = re.compile(r'(?:\.\./){2,}')

    # 危险路径写入模式
    DANGEROUS_WRITE_PATTERNS = [
        (r'>\s*/dev/sd[a-z]', "直接写磁盘设备"),
        (r'>>\s*/dev/sd[a-z]', "追加写磁盘设备"),
        (r'>\s*/dev/tty', "直接写 TTY 设备"),
        (r'>\s*/proc/\d+/mem', "直接写进程内存"),
    ]

    def __init__(self):
        self.threats: List[Dict[str, Any]] = []

    def analyze(self, command: str) -> Dict[str, Any]:
        """
        主分析函数
        1. 词法分析 → token 流
        2. AST 解析 → 语法树
        3. 安全分析 → 威胁列表
        """
        self.threats = []
        if not command or not command.strip():
            return self._safe_result("空命令")

        # Stage 1: 零宽字符检测（任何语言层面）
        if re.search(r'[\u200b\u200c\u200d\ufeff]', command):
            return self._unsafe_result(
                "ZERO_WIDTH_CHAR",
                "零宽字符注入 — 可能在终端隐藏命令内容",
                re.search(r'[\u200b\u200c\u200d\ufeff]', command).group()
            )

        # Stage 2: 尝试解析 AST
        ast = None
        try:
            lexer = Lexer(command)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            ast = parser.parse()
        except Exception as e:
            return self._parse_failed_result(
                "AST_PARSE_ERROR",
                f"AST 解析失败: {e}",
                str(e)
            )

        # Stage 3: AST 安全分析
        self._analyze_ast(ast, command)

        if self.threats:
            worst = self.threats[0]
            return {
                "threat": Threat.UNSAFE,
                "level": worst["type"],
                "reason": worst["reason"],
                "detail": worst["detail"],
                "ast": ast.to_dict() if ast else None,
            }

        return {
            "threat": Threat.SAFE,
            "level": "CLEAR",
            "reason": f"命令安全",
            "detail": self._get_command_summary(ast),
            "ast": ast.to_dict() if ast else None,
        }

    def _analyze_ast(self, node: ASTNode, command: str):
        """递归分析 AST 节点"""
        if node is None:
            return

        # 检查危险命令
        if node.type == NodeType.COMMAND:
            self._check_dangerous_command(node, command)

        # 检查路径遍历（只看 ARG 类型）
        if node.type == NodeType.ARG:
            self._check_path_traversal(node.value, command)

        # 检查注入（命令链）
        if node.type == NodeType.COMMAND_CHAIN:
            self._check_injection_chain(node, command)

        # 检查 pipeline 到 shell
        if node.type == NodeType.PIPELINE:
            self._check_pipe_to_shell(node, command)

        # 检查危险写入目标
        if node.type == NodeType.REDIRECTION:
            self._check_dangerous_redirect(node.value, command)

        # 递归检查子节点
        for child in node.children:
            self._analyze_ast(child, command)

    def _check_dangerous_command(self, node: ASTNode, command: str):
        """检查危险命令"""
        if not node.children:
            return

        first_arg = None
        for child in node.children:
            if child.type == NodeType.ARG and child.value:
                first_arg = child.value
                break
            elif child.type == NodeType.WORD and child.value and not child.value.startswith('$'):
                first_arg = child.value
                break

        if not first_arg:
            return

        # 获取完整命令名（去掉路径）
        cmd_name = first_arg.split('/')[-1]

        if cmd_name in self.DANGEROUS_COMMANDS:
            # 构建完整命令字符串
            all_args = []
            for child in node.children:
                if child.type == NodeType.ARG:
                    all_args.append(child.value)
                elif child.type == NodeType.WORD and not child.value.startswith('$'):
                    all_args.append(child.value)

            full_cmd = " ".join(all_args)

            # 特殊情况：rm 递归删除
            if cmd_name == "rm" and any(a in full_cmd for a in ["-rf", "-r", "-f", "-R"]):
                self._add_threat("HIGH_RISK", f"rm 递归删除: {full_cmd[:60]}", full_cmd[:80])
                return

            # 特殊情况：chmod 777
            if cmd_name == "chmod" and "777" in full_cmd:
                self._add_threat("HIGH_RISK", f"chmod 777 全权限: {full_cmd[:60]}", full_cmd[:80])
                return

            # 特殊情况：dd 命令
            if cmd_name == "dd":
                self._add_threat("HIGH_RISK", f"dd 原始磁盘操作: {full_cmd[:60]}", full_cmd[:80])
                return

            # curl/wget pipe to shell
            if cmd_name in ("curl", "wget") and "|" in command:
                pipe_match = re.search(r'\|.*(?:bash|sh|zsh|perl|python|ruby)', command, re.IGNORECASE)
                if pipe_match:
                    self._add_threat("HIGH_RISK", f"{cmd_name} | bash — 下载并执行攻击模式", pipe_match.group())
                    return

            # 一般危险命令
            risk = "HIGH_RISK" if cmd_name in {"rm", "dd", "mkfs", "chmod", "curl", "wget", "eval", "exec", "source"} else "MEDIUM_RISK"
            self._add_threat(risk, f"危险命令: {cmd_name}", full_cmd[:60])

    def _check_path_traversal(self, value: str, command: str):
        """检查路径遍历和敏感路径"""
        if not value:
            return

        # 过滤掉变量扩展部分
        clean_value = re.sub(r'\$\{[^}]+\}', '', value)
        clean_value = re.sub(r'\$[a-zA-Z_][a-zA-Z0-9_]*', '', clean_value)

        # 检查 ../ 过多
        dotdot_count = clean_value.count('../')
        if dotdot_count >= 3:
            self._add_threat("MEDIUM_RISK", f"路径遍历 ../ 过多 ({dotdot_count}次)", value)
            return

        # 检查敏感路径
        for pattern, desc in self.SENSITIVE_PATHS:
            if re.search(pattern, clean_value):
                # 特例：/dev/null 是安全的
                if "/dev/null" in clean_value:
                    continue
                self._add_threat("HIGH_RISK", f"敏感路径: {desc}", value)
                return

    def _check_injection_chain(self, node: ASTNode, command: str):
        """检查命令链注入攻击"""
        # 解析 && || ; 后的命令
        if not node.children:
            return

        for i, child in enumerate(node.children):
            if child.type != NodeType.COMMAND:
                continue
            if not child.children:
                continue

            # 获取命令名
            first_word = None
            for c in child.children:
                if c.type == NodeType.ARG and c.value:
                    first_word = c.value.split('/')[-1]
                    break
                if c.type == NodeType.WORD and c.value and not c.value.startswith('$'):
                    first_word = c.value.split('/')[-1]
                    break

            if not first_word:
                continue

            # && || 后的危险命令
            if node.value in ('&&', '||', ';') and i > 0:
                dangerous = {"curl", "wget", "nc", "bash", "sh", "zsh", "eval", "exec", "python", "ruby", "perl"}
                if first_word in dangerous:
                    self._add_threat("HIGH_RISK", f"命令链 {node.value} 后的危险命令: {first_word}", command[:80])

    def _check_pipe_to_shell(self, node: ASTNode, command: str):
        """检查管道到 shell 的攻击模式"""
        if not node.children:
            return

        cmd_names = []
        for child in node.children:
            if child.type == NodeType.COMMAND:
                for c in child.children:
                    if c.type == NodeType.ARG and c.value:
                        cmd_names.append(c.value.split('/')[-1])
                        break
                    if c.type == NodeType.WORD and c.value and not c.value.startswith('$'):
                        cmd_names.append(c.value.split('/')[-1])
                        break

        # curl/wget + | + shell
        if any(c in cmd_names for c in ("curl", "wget")):
            pipe_shell = re.search(r'\|[^|]*(bash|sh|zsh|perl|python|ruby)', command, re.IGNORECASE)
            if pipe_shell:
                self._add_threat("HIGH_RISK", f"curl/wget pipe 到 shell — 典型远程代码执行攻击", pipe_shell.group())

    def _check_dangerous_redirect(self, value: str, command: str):
        """检查危险的重定向目标"""
        for pattern, desc in self.DANGEROUS_WRITE_PATTERNS:
            if re.search(pattern, command):
                self._add_threat("CRITICAL_RISK", f"危险重定向: {desc}", re.search(pattern, command).group())

    def _add_threat(self, type_: str, reason: str, detail: str):
        """添加一个威胁（只保留最高风险的）"""
        # 风险等级映射
        risk_order = {"CRITICAL_RISK": 0, "HIGH_RISK": 1, "MEDIUM_RISK": 2, "LOW_RISK": 3}

        new_risk = risk_order.get(type_, 99)
        existing_risk = risk_order.get(self.threats[0]["type"], 99) if self.threats else 99

        if new_risk <= existing_risk:
            if new_risk < existing_risk:
                self.threats.insert(0, {"type": type_, "reason": reason, "detail": detail})
            else:
                self.threats.append({"type": type_, "reason": reason, "detail": detail})

    def _get_command_summary(self, ast: ASTNode) -> str:
        """从 AST 提取命令摘要"""
        if not ast or not ast.children:
            return ""
        first_cmd = ast.children[0]
        if first_cmd.type == NodeType.COMMAND:
            parts = []
            for c in first_cmd.children:
                if c.type == NodeType.ARG:
                    parts.append(c.value)
                elif c.type == NodeType.WORD:
                    parts.append(c.value)
            return " ".join(parts[:5])
        return ""

    def _safe_result(self, reason: str) -> Dict[str, Any]:
        return {"threat": Threat.SAFE, "level": "CLEAR", "reason": reason, "detail": "", "ast": None}

    def _unsafe_result(self, level: str, reason: str, detail: str) -> Dict[str, Any]:
        return {"threat": Threat.UNSAFE, "level": level, "reason": reason, "detail": detail, "ast": None}

    def _parse_failed_result(self, level: str, reason: str, detail: str) -> Dict[str, Any]:
        return {"threat": Threat.PARSE_FAILED, "level": level, "reason": reason, "detail": detail, "ast": None}


# ─── 入口函数 ────────────────────────────────────────────────────────────────

def analyze(command: str) -> Dict[str, Any]:
    """对外暴露的分析接口"""
    analyzer = BashASTAnalyzer()
    return analyzer.analyze(command)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 bash_ast.py '<command>'")
        print("返回码: 0=SAFE, 1=PARSE_FAILED, 2=UNSAFE")
        sys.exit(0)

    command = " ".join(sys.argv[1:])
    result = analyze(command)

    # 友好输出
    icon = {0: "✅", 1: "⚠️", 2: "🚫"}
    icon_char = icon.get(result["threat"], "❓")
    print(f"{icon_char} [{result['level']}] {result['reason']}")
    if result.get("detail"):
        print(f"   详情: {result['detail']}")

    # 可选：JSON 输出（通过环境变量控制）
    if os.environ.get("BASH_AST_JSON"):
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(result["threat"])


if __name__ == "__main__":
    import os
    main()
