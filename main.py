"""
DLsite 下载器
基于 dlsite-async 库实现的 DLsite 电子书下载工具
支持登录、浏览购买的图书作品、选择下载
"""

import asyncio
import os
import sys
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Tuple, Dict, Optional
from getpass import getpass

# 设置标准输出编码为UTF-8，解决Windows下中文显示问题
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from dlsite_async import PlayAPI, EbookSession
    import dlsite_async
    print(f"使用 dlsite-async 版本: {getattr(dlsite_async, '__version__', '未知版本')}")
except ImportError:
    print("错误：请先安装依赖库")
    print("运行命令：pip install -r requirements.txt")
    print("如果还有问题，请尝试：pip install git+https://github.com/bhrevol/dlsite-async.git")
    sys.exit(1)


class DLsiteDownloader:
    """DLsite 下载器主类"""
    
    def __init__(self):
        self.play_api = None
        self.book_works = []
        self.user_data_file = "dlsite_user_data.json"  # 合并的用户数据文件
        self.filtered_works = []  # 用于搜索过滤后的作品
        self.search_mode = False  # 是否处于搜索模式
        self.proxy_config = None  # 存储代理配置
        self.setup_logging()
        self.detect_and_setup_proxy()  # 检测并设置系统代理
    
    def setup_logging(self):
        """设置日志系统"""
        # 创建日志记录器
        self.logger = logging.getLogger('DLsiteDownloader')
        self.logger.setLevel(logging.DEBUG)
        
        # 如果已经有处理器，清除它们
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 创建文件处理器
        file_handler = logging.FileHandler('dlsite_downloader.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # 创建控制台处理器（仅显示重要信息）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 创建格式化器
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_formatter = logging.Formatter('%(message)s')
        
        # 设置格式化器
        file_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)
        
        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        print("日志系统已启用，详细信息保存到 dlsite_downloader.log")
    
    def detect_and_setup_proxy(self) -> None:
        """检测并设置系统代理"""
        try:
            print("检测系统代理设置...")
            
            # 检测 Windows 系统代理
            proxy_info = self.get_windows_proxy()
            
            if proxy_info:
                proxy_url, proxy_description = proxy_info
                print(f"检测到系统代理：{proxy_description}")
                
                # 测试代理连接
                if self.test_proxy_connection(proxy_url):
                    self.proxy_config = proxy_url
                    print(f"将使用代理：{proxy_url}")
                    self.logger.info(f"检测到系统代理并测试通过：{proxy_url}")
                else:
                    print(f"代理连接测试失败，将尝试直连")
                    self.logger.warning(f"代理连接测试失败：{proxy_url}")
                    self.proxy_config = None
            else:
                # 尝试通过环境变量检测代理
                env_proxy = self.get_env_proxy()
                if env_proxy:
                    print(f"检测到环境变量代理：{env_proxy}")
                    if self.test_proxy_connection(env_proxy):
                        self.proxy_config = env_proxy
                        print(f"将使用环境变量代理：{env_proxy}")
                        self.logger.info(f"使用环境变量代理并测试通过：{env_proxy}")
                    else:
                        print(f"环境变量代理连接测试失败，将尝试直连")
                        self.logger.warning(f"环境变量代理连接测试失败：{env_proxy}")
                        self.proxy_config = None
                else:
                    print("未检测到系统代理设置")
                    self.logger.info("未检测到系统代理")
                    
        except Exception as e:
            print(f"代理检测出错：{str(e)}")
            self.logger.warning(f"代理检测失败：{str(e)}")
            self.proxy_config = None
    
    def get_windows_proxy(self) -> Optional[Tuple[str, str]]:
        """获取 Windows 系统代理设置"""
        try:
            import winreg
            
            # 尝试读取 Windows 注册表中的代理设置
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
                try:
                    # 检查是否启用了代理
                    proxy_enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
                    if proxy_enable:
                        # 获取代理服务器地址
                        proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0]
                        
                        # 解析代理地址
                        if '=' in proxy_server:
                            # 如果有协议特定的代理设置
                            proxy_dict = {}
                            for proxy_entry in proxy_server.split(';'):
                                if '=' in proxy_entry:
                                    protocol, address = proxy_entry.split('=', 1)
                                    proxy_dict[protocol] = address
                            
                            # 优先使用 HTTP 代理
                            if 'http' in proxy_dict:
                                proxy_url = f"http://{proxy_dict['http']}"
                                return proxy_url, f"HTTP 代理 - {proxy_dict['http']}"
                            elif 'https' in proxy_dict:
                                proxy_url = f"http://{proxy_dict['https']}"
                                return proxy_url, f"HTTPS 代理 - {proxy_dict['https']}"
                        else:
                            # 单一代理服务器
                            proxy_url = f"http://{proxy_server}"
                            return proxy_url, f"代理服务器 - {proxy_server}"
                except FileNotFoundError:
                    pass
                    
        except ImportError:
            # 如果不是 Windows 系统或无法导入 winreg
            pass
        except Exception as e:
            self.logger.debug(f"读取 Windows 代理设置失败：{str(e)}")
            
        return None
    
    def get_env_proxy(self) -> Optional[str]:
        """从环境变量获取代理设置"""
        try:
            # 检查常见的代理环境变量
            proxy_vars = ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy']
            
            for var in proxy_vars:
                proxy = os.environ.get(var)
                if proxy:
                    return proxy
                    
        except Exception as e:
            self.logger.debug(f"读取环境变量代理失败：{str(e)}")
            
        return None
    
    def test_proxy_connection(self, proxy_url: str) -> bool:
        """测试代理连接是否可用"""
        try:
            import socket
            import urllib.request
            from urllib.parse import urlparse
            
            # 解析代理地址
            parsed = urlparse(proxy_url)
            proxy_host = parsed.hostname
            proxy_port = parsed.port
            
            if not proxy_host or not proxy_port:
                self.logger.debug(f"代理地址解析失败：{proxy_url}")
                return False
            
            # 先测试代理服务器是否可达
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)  # 5秒超时
                result = sock.connect_ex((proxy_host, proxy_port))
                sock.close()
                
                if result != 0:
                    self.logger.debug(f"代理服务器不可达：{proxy_host}:{proxy_port}")
                    return False
                    
            except Exception as e:
                self.logger.debug(f"代理连接测试失败：{str(e)}")
                return False
            
            # 如果基本连接测试通过，尝试通过代理访问一个简单的网站
            try:
                proxy_handler = urllib.request.ProxyHandler({
                    'http': proxy_url,
                    'https': proxy_url
                })
                opener = urllib.request.build_opener(proxy_handler)
                
                # 设置超时
                request = urllib.request.Request('http://httpbin.org/ip')
                request.add_header('User-Agent', 'DLsite-Downloader/1.0')
                
                with opener.open(request, timeout=10) as response:
                    if response.status == 200:
                        self.logger.debug(f"代理连接测试成功：{proxy_url}")
                        return True
                        
            except Exception as e:
                self.logger.debug(f"代理HTTP测试失败：{str(e)}")
                # 即使HTTP测试失败，如果基本连接成功，仍然尝试使用代理
                # 因为可能是目标网站不可达的问题
                self.logger.debug("基本连接成功，将尝试使用代理")
                return True
                
        except Exception as e:
            self.logger.debug(f"代理测试出错：{str(e)}")
            
        return False
    
    def create_play_api(self) -> PlayAPI:
        """创建配置了代理的 PlayAPI 实例"""
        try:
            if self.proxy_config:
                print(f"使用代理配置：{self.proxy_config}")
                self.logger.info(f"创建 PlayAPI 实例，使用代理：{self.proxy_config}")
                
                # 创建带代理的 PlayAPI 实例
                # 注意：需要检查 dlsite-async 库的具体 API
                try:
                    # 尝试使用代理参数创建 PlayAPI
                    return PlayAPI(proxy=self.proxy_config)
                except TypeError:
                    # 如果 PlayAPI 不支持 proxy 参数，尝试其他方法
                    print("PlayAPI 不支持直接代理参数，将尝试设置环境变量")
                    
                    # 解析代理 URL
                    from urllib.parse import urlparse
                    parsed = urlparse(self.proxy_config)
                    
                    if parsed.hostname and parsed.port:
                        # 设置环境变量
                        proxy_env = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                        os.environ['HTTP_PROXY'] = proxy_env
                        os.environ['HTTPS_PROXY'] = proxy_env
                        print(f"已设置代理环境变量：{proxy_env}")
                        self.logger.info(f"设置代理环境变量：{proxy_env}")
                    
                    return PlayAPI()
            else:
                print("使用直连模式")
                self.logger.info("创建 PlayAPI 实例，直连模式")
                return PlayAPI()
                
        except Exception as e:
            print(f"创建 PlayAPI 时出错：{str(e)}")
            print("将使用默认配置")
            self.logger.warning(f"创建 PlayAPI 失败，使用默认配置：{str(e)}")
            return PlayAPI()
    
    def save_user_data(self, save_credentials: bool = False, save_session: bool = False, 
                      username: str = None, password: str = None) -> None:
        """保存用户数据到本地文件"""
        try:
            # 加载现有数据
            user_data = self.load_user_data() or {}
            
            # 更新凭据信息
            if save_credentials and username and password:
                user_data["credentials"] = {
                    "username": username,
                    "password": password,
                    "last_login": asyncio.get_event_loop().time()
                }
                print("账号密码已保存")
            
            # 更新会话信息
            if save_session and self.play_api and hasattr(self.play_api, 'session'):
                session_data = {}
                
                # 保存 cookies
                if hasattr(self.play_api.session, 'cookie_jar'):
                    cookies = {}
                    for cookie in self.play_api.session.cookie_jar:
                        cookies[cookie.key] = {
                            'value': cookie.value,
                            'domain': cookie['domain'],
                            'path': cookie['path']
                        }
                    session_data['cookies'] = cookies
                
                # 保存其他会话信息
                if hasattr(self.play_api, '_headers'):
                    session_data['headers'] = dict(self.play_api._headers)
                elif hasattr(self.play_api, 'session') and hasattr(self.play_api.session, '_default_headers'):
                    session_data['headers'] = dict(self.play_api.session._default_headers)
                
                # 保存时间戳
                session_data['timestamp'] = asyncio.get_event_loop().time()
                user_data["session"] = session_data
                print("会话信息已保存")
            
            # 保存到文件
            with open(self.user_data_file, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False)
            print(f"用户数据已保存到 {self.user_data_file}")
            
        except Exception as e:
            print(f"保存用户数据失败：{str(e)}")
    
    def load_user_data(self) -> Optional[Dict]:
        """从本地文件加载用户数据"""
        try:
            if os.path.exists(self.user_data_file):
                with open(self.user_data_file, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                return user_data
        except Exception as e:
            print(f"加载用户数据失败：{str(e)}")
        return None
    
    def load_credentials(self) -> Optional[Dict[str, str]]:
        """从用户数据中加载凭据"""
        user_data = self.load_user_data()
        if user_data and "credentials" in user_data:
            print(f"从 {self.user_data_file} 加载已保存的凭据")
            return user_data["credentials"]
        return None
    
    def load_session(self) -> bool:
        """加载已保存的会话信息"""
        try:
            user_data = self.load_user_data()
            if user_data and "session" in user_data:
                session_data = user_data["session"]
                
                # 检查会话是否过期（7天）
                current_time = asyncio.get_event_loop().time()
                if current_time - session_data.get('timestamp', 0) > 7 * 24 * 3600:
                    print("会话已过期，需要重新登录")
                    # 删除过期的session数据
                    user_data.pop("session", None)
                    with open(self.user_data_file, 'w', encoding='utf-8') as f:
                        json.dump(user_data, f, indent=2, ensure_ascii=False)
                    return False
                
                print(f"从 {self.user_data_file} 加载会话信息")
                return True
        except Exception as e:
            print(f"加载会话失败：{str(e)}")
        return False
    
    def clear_saved_data(self, clear_credentials: bool = True, clear_session: bool = True) -> None:
        """清除保存的凭据和会话信息"""
        try:
            if os.path.exists(self.user_data_file):
                user_data = self.load_user_data() or {}
                
                if clear_credentials and "credentials" in user_data:
                    user_data.pop("credentials", None)
                    print("已清除保存的账号密码")
                
                if clear_session and "session" in user_data:
                    user_data.pop("session", None)
                    print("已清除保存的会话信息")
                
                if not user_data:
                    # 如果文件为空，直接删除
                    os.remove(self.user_data_file)
                    print(f"已删除 {self.user_data_file}")
                else:
                    # 否则保存剩余数据
                    with open(self.user_data_file, 'w', encoding='utf-8') as f:
                        json.dump(user_data, f, indent=2, ensure_ascii=False)
                    print(f"已更新 {self.user_data_file}")
            
            # 兼容性：清理旧文件
            for old_file in ["dlsite_credentials.json", "dlsite_session.json"]:
                if os.path.exists(old_file):
                    os.remove(old_file)
                    print(f"已删除旧文件：{old_file}")
                    
        except Exception as e:
            print(f"清除数据失败：{str(e)}")
        
    async def login(self) -> bool:
        """用户登录功能"""
        print("=" * 50)
        print("欢迎使用 DLsite 下载器")
        print("=" * 50)
        
        # 尝试加载已保存的凭据
        saved_credentials = self.load_credentials()
        if saved_credentials:
            print("检测到已保存的登录信息，尝试自动登录...")
            username = saved_credentials.get('username')
            password = saved_credentials.get('password')
            
            if username and password:
                try:
                    print("正在使用保存的凭据登录...")
                    self.play_api = self.create_play_api()
                    await self.play_api.login(username, password)
                    print("自动登录成功！")
                    # 保存新的会话信息（保持原有的凭据）
                    self.save_user_data(save_session=True)
                    return True
                except Exception as e:
                    print(f"自动登录失败：{str(e)}")
                    print("将尝试手动登录...")
                    # 清除可能无效的凭据
                    self.clear_saved_data()
        
        # 手动登录流程
        print("\n请输入您的 DLsite 登录信息：")
        print("提示：登录成功后，凭据将保存到本地以便下次自动登录")
        
        while True:
            username = input("用户名/邮箱：").strip()
            if username:
                break
            print("用户名不能为空，请重新输入")
        
        while True:
            password = getpass("密码：")
            if password:
                break
            print("密码不能为空，请重新输入")
        
        try:
            print("正在登录中...")
            self.play_api = self.create_play_api()
            await self.play_api.login(username, password)
            print("登录成功！")
            
            # 分别询问是否保存凭据和会话
            print("\n请选择要保存的信息：")
            save_credentials = input("是否保存账号密码以便下次自动登录？(y/n)：").strip().lower() in ['y', 'yes', '是']
            save_session = input("是否保存会话信息以减少登录频率？(y/n)：").strip().lower() in ['y', 'yes', '是']
            
            if save_credentials or save_session:
                self.save_user_data(
                    save_credentials=save_credentials,
                    save_session=save_session,
                    username=username if save_credentials else None,
                    password=password if save_credentials else None
                )
            else:
                print("未保存任何登录信息，下次需要重新输入")
            
            return True
            
        except Exception as e:
            print(f"登录失败：{str(e)}")
            return False
    
    async def get_purchased_books(self) -> List:
        """获取用户购买的图书类作品"""
        print("\n正在获取您购买的作品...")
        
        try:
            # 获取所有购买记录
            purchases = []
            async for work, release_date in self.play_api.purchases():
                purchases.append((work, release_date))
            
            # 筛选图书类作品
            self.book_works = [
                (work, release_date) for work, release_date in purchases
                if work.work_type in ["MNG", "BOOK"]
            ]
            
            print(f"找到 {len(self.book_works)} 个图书类作品")
            return self.book_works
            
        except Exception as e:
            print(f"获取作品列表失败：{str(e)}")
            return []
    
    def display_books(self, page: int = 1, per_page: int = 200) -> dict:
        """分页显示图书作品列表"""
        if not self.book_works:
            print("您还没有购买任何图书类作品。")
            return {"total_pages": 0, "current_page": 0, "has_next": False, "has_prev": False}
        
        # 获取当前应该显示的作品列表
        current_works = self.get_current_works_list()
        
        if not current_works and self.search_mode:
            print("没有找到匹配的作品。")
            return {"total_pages": 0, "current_page": 0, "has_next": False, "has_prev": False}
        
        total_works = len(current_works)
        total_pages = (total_works + per_page - 1) // per_page  # 向上取整
        
        # 确保页码在有效范围内
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_works)
        current_page_works = current_works[start_idx:end_idx]
        
        print("\n" + "=" * 80)
        if self.search_mode:
            print(f"搜索结果 (第 {page}/{total_pages} 页，共 {total_works} 部)")
        else:
            print(f"您购买的图书类作品 (第 {page}/{total_pages} 页，共 {total_works} 部)")
        print("=" * 80)
        print("提示：程序会自动尝试下载所有可用文件")
        user_data = self.load_user_data()
        if user_data:
            info_parts = []
            if "credentials" in user_data:
                info_parts.append("账号密码")
            if "session" in user_data:
                info_parts.append("会话信息")
            if info_parts:
                print(f"已保存{' 和 '.join(info_parts)}，下次启动将自动登录")
        print("=" * 80)
        
        for i, (work, release_date) in enumerate(current_page_works):
            global_idx = start_idx + i + 1
            print(f"{global_idx:3d}. [{work.product_id}] {work.work_name}")
            print(f"     发售日期：{release_date.strftime('%Y-%m-%d')}")
            print(f"     作品类型：{work.work_type}")
            print("-" * 80)
        
        # 显示分页信息
        if total_pages > 1:
            print(f"\n分页导航：")
            nav_info = []
            if page > 1:
                nav_info.append("输入 'prev' 或 'p' 查看上一页")
            if page < total_pages:
                nav_info.append("输入 'next' 或 'n' 查看下一页")
            if nav_info:
                print("  " + " | ".join(nav_info))
            print(f"  输入 'page X' 跳转到第 X 页 (1-{total_pages})")
        
        return {
            "total_pages": total_pages,
            "current_page": page,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "total_works": total_works
        }
    
    def search_works(self, keyword: str) -> int:
        """搜索作品
        返回匹配的作品数量
        """
        keyword_lower = keyword.lower()
        self.filtered_works = []
        
        for work, release_date in self.book_works:
            # 在作品名称和产品ID中搜索
            if (keyword_lower in work.work_name.lower() or 
                keyword_lower in work.product_id.lower()):
                self.filtered_works.append((work, release_date))
        
        self.search_mode = len(self.filtered_works) > 0
        return len(self.filtered_works)
    
    def get_current_works_list(self):
        """获取当前应该显示的作品列表"""
        return self.filtered_works if self.search_mode else self.book_works
    
    def get_user_choice(self, page_info: dict) -> tuple:
        """获取用户选择的作品序号或分页命令
        返回: (action_type, value)
        action_type: 'download', 'exit', 'clear', 'next_page', 'prev_page', 'goto_page'
        """
        while True:
            try:
                print(f"\n请选择操作：")
                print(f"  输入作品序号 (1-{len(self.book_works)}) 下载作品")
                print(f"  输入 0 退出程序")
                print(f"  输入 'clear' 清除所有保存的登录信息")
                print(f"  输入 'clear credentials' 仅清除账号密码")
                print(f"  输入 'clear session' 仅清除会话信息")
                print(f"  输入 'search 关键词' 搜索作品")
                if self.search_mode:
                    print(f"  输入 'reset' 退出搜索模式")
                
                
                choice = input("请选择：").strip().lower()
                
                if choice == "0":
                    return ("exit", 0)
                elif choice == 'clear':
                    self.clear_saved_data()
                    continue
                elif choice == 'clear credentials':
                    self.clear_saved_data(clear_credentials=True, clear_session=False)
                    continue
                elif choice == 'clear session':
                    self.clear_saved_data(clear_credentials=False, clear_session=True)
                    continue
                elif choice == 'reset' and self.search_mode:
                    return ("reset_search", 0)
                elif choice.startswith('search '):
                    keyword = choice[7:].strip()
                    if keyword:
                        return ("search", keyword)
                    else:
                        print("请输入搜索关键词，例如：search 关键词")
                        continue
                elif choice in ['next', 'n'] and page_info["has_next"]:
                    return ("next_page", page_info["current_page"] + 1)
                elif choice in ['prev', 'p'] and page_info["has_prev"]:
                    return ("prev_page", page_info["current_page"] - 1)
                elif choice.startswith('page '):
                    try:
                        target_page = int(choice.split()[1])
                        if 1 <= target_page <= page_info["total_pages"]:
                            return ("goto_page", target_page)
                        else:
                            print(f"页码必须在 1 到 {page_info['total_pages']} 之间")
                            continue
                    except (IndexError, ValueError):
                        print("格式错误，请使用 'page X' 格式，例如 'page 3'")
                        continue
                else:
                    try:
                        choice_num = int(choice)
                        max_num = len(self.get_current_works_list())
                        if 1 <= choice_num <= max_num:
                            # 如果在搜索模式，需要找到对应的原始索引
                            if self.search_mode:
                                selected_work = self.filtered_works[choice_num - 1][0]
                                # 在原始列表中找到这个作品的索引
                                for i, (work, _) in enumerate(self.book_works):
                                    if work.product_id == selected_work.product_id:
                                        return ("download", i)
                            else:
                                return ("download", choice_num - 1)  # 转换为数组索引
                        else:
                            print(f"请输入 1 到 {max_num} 之间的数字")
                    except ValueError:
                        print("请输入有效的数字或命令")
                        
            except Exception as e:
                print(f"输入处理出错：{str(e)}")
                print("请重新输入")
    
    async def download_work(self, work_index: int) -> bool:
        """下载指定的作品"""
        work, _ = self.book_works[work_index]
        product_id = work.product_id
        work_name = work.work_name
        
        print(f"\n开始下载：{work_name} (ID: {product_id})")
        
        try:
            # 获取下载令牌
            print("正在获取下载令牌...")
            token = await self.play_api.download_token(product_id)
            
            # 获取作品文件树
            print("正在获取文件信息...")
            tree = await self.play_api.ziptree(token)
            
            # 创建下载目录
            safe_name = "".join(c for c in work_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            download_dir = f"downloads/{safe_name}_{product_id}"
            os.makedirs(download_dir, exist_ok=True)
            
            # 检查所有可用文件
            all_files = list(tree.items())
            
            self.logger.info(f"作品 {product_id} 文件分析开始")
            self.logger.debug(f"总共找到 {len(all_files)} 个文件")
            
            if not all_files:
                print("该作品没有任何可下载的文件")
                print("\n可能的原因:")
                print("   1. 该作品仅支持 DLsite Play 在线阅览")
                print("   2. 作品可能已被下架或限制访问")
                print("   3. 网络连接问题")
                self.logger.warning(f"作品 {product_id} 没有找到任何文件")
                return False
            
            # 详细分析每个文件
            self.logger.debug("开始详细分析每个文件:")
            for idx, (filename, playfile) in enumerate(all_files):
                self.logger.debug(f"文件 {idx+1}: {filename}")
                self.logger.debug(f"  - 文件类型: {type(playfile).__name__}")
                self.logger.debug(f"  - is_ebook 属性: {getattr(playfile, 'is_ebook', 'N/A')}")
                self.logger.debug(f"  - 文件扩展名: {os.path.splitext(filename)[1].lower()}")
                
                # 检查更多属性
                for attr in ['url', 'size', 'encrypted', 'scrambled', 'type', 'content_type', 'mime_type']:
                    if hasattr(playfile, attr):
                        self.logger.debug(f"  - {attr}: {getattr(playfile, attr)}")
                
                # 列出所有可用属性
                all_attrs = [attr for attr in dir(playfile) if not attr.startswith('_')]
                self.logger.debug(f"  - 所有属性: {all_attrs}")
            
            # 分类文件类型
            ebook_files = []
            cpd_files = []
            pdf_files = []
            other_files = []
            potentially_scrambled_images = []
            
            for filename, playfile in all_files:
                is_ebook = getattr(playfile, 'is_ebook', False)
                file_ext = filename.lower()
                
                if is_ebook:
                    ebook_files.append((filename, playfile))
                    self.logger.debug(f"{filename} 识别为电子书文件")
                elif file_ext.endswith('.cpd'):
                    cpd_files.append((filename, playfile))
                    self.logger.debug(f"{filename} 识别为 CPD 文件")
                elif file_ext.endswith('.pdf'):
                    pdf_files.append((filename, playfile))
                    self.logger.debug(f"{filename} 识别为 PDF 文件")
                elif file_ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    # 检查是否可能是需要解密的图片
                    is_scrambled = getattr(playfile, 'scrambled', False) or getattr(playfile, 'encrypted', False)
                    has_descramble = hasattr(playfile, 'descramble')
                    
                    # 对于漫画作品，如果是按页命名的图片文件，很可能需要解密
                    is_likely_comic_page = (
                        # 数字开头的文件名
                        filename.lower().startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')) and
                        # 包含位置标识符
                        any(keyword in filename.lower() for keyword in ['left', 'right', 'center', '_'])
                    )
                    
                    # 额外检查：如果所有文件都是数字命名的图片，可能都需要解密
                    is_numbered_pattern = len([f for f, _ in all_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]) > 5
                    is_numbered_file = filename.lower().startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9'))
                    
                    # 如果文件名看起来像页面序号，且作品有很多数字命名的图片文件
                    is_potential_scrambled = is_numbered_pattern and is_numbered_file
                    
                    if is_scrambled or has_descramble or is_likely_comic_page or is_potential_scrambled:
                        potentially_scrambled_images.append((filename, playfile))
                        reason = []
                        if is_scrambled: reason.append("标记为混淆")
                        if has_descramble: reason.append("有解密方法")
                        if is_likely_comic_page: reason.append("疑似漫画页面")
                        if is_potential_scrambled: reason.append("数字命名模式")
                        self.logger.debug(f"{filename} 可能需要解密处理 - 原因: {', '.join(reason)}")
                    else:
                        other_files.append((filename, playfile))
                        self.logger.debug(f"{filename} 识别为普通图片文件")
                else:
                    other_files.append((filename, playfile))
                    self.logger.debug(f"{filename} 识别为其他文件")
            
            self.logger.info(f"文件分类结果: 电子书={len(ebook_files)}, CPD={len(cpd_files)}, PDF={len(pdf_files)}, 可能需解密图片={len(potentially_scrambled_images)}, 其他={len(other_files)}")
            
            # 显示文件分析
            print(f"文件分析结果（共 {len(all_files)} 个文件）：")
            if ebook_files:
                print(f"  电子书文件：{len(ebook_files)} 个")
            if cpd_files:
                print(f"  CypherGuard PDF：{len(cpd_files)} 个")
            if pdf_files:
                print(f"  PDF 文件：{len(pdf_files)} 个")
            if potentially_scrambled_images:
                print(f"  需解密图片：{len(potentially_scrambled_images)} 个")
            if other_files:
                print(f"  其他文件：{len(other_files)} 个")
            
            print("\n完整文件列表：")
            for filename, playfile in all_files:
                is_ebook = getattr(playfile, 'is_ebook', False)
                file_ext = filename.lower()
                
                if is_ebook:
                    file_type = "电子书"
                elif file_ext.endswith('.cpd'):
                    file_type = "CPD"
                elif file_ext.endswith('.pdf'):
                    file_type = "PDF"
                elif file_ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    is_scrambled = getattr(playfile, 'scrambled', False) or getattr(playfile, 'encrypted', False)
                    if is_scrambled or hasattr(playfile, 'descramble'):
                        file_type = "需解密图片"
                    else:
                        file_type = "普通图片"
                else:
                    file_type = "其他"
                    
                print(f"  - {filename} ({file_type})")
            
            print(f"\n是否下载所有 {len(all_files)} 个文件？")
            choice = input("输入 y 继续下载，输入 n 取消：").strip().lower()
            if choice not in ['y', 'yes', '是']:
                print("已取消下载")
                return False
            
            print(f"\n开始下载 {len(all_files)} 个文件...")
            downloaded_count = 0
            
            # 优先处理电子书文件（需要特殊解密）
            if ebook_files:
                print(f"\n处理 {len(ebook_files)} 个电子书文件...")
                for file_idx, (filename, playfile) in enumerate(ebook_files, 1):
                    print(f"[电子书 {file_idx}/{len(ebook_files)}] 处理：{filename}")
                    
                    try:
                        # 创建文件专用目录
                        ebook_dir = os.path.join(download_dir, f"ebook_{os.path.splitext(filename)[0]}")
                        
                        async with EbookSession(self.play_api, tree, playfile) as ebook:
                            print(f"  页数：{ebook.page_count}")
                            
                            # 下载所有页面
                            for page_num in range(ebook.page_count):
                                print(f"  下载页面 {page_num + 1}/{ebook.page_count}...", end="\r")
                                try:
                                    # 尝试使用新版本的 API
                                    await ebook.download_page(page_num, ebook_dir, mkdir=True, force=True)
                                except TypeError:
                                    # 如果失败，尝试不带 descramble 参数
                                    await ebook.download_page(page_num, ebook_dir, mkdir=True)
                                except Exception as e:
                                    # 如果还是失败，尝试最基本的调用
                                    try:
                                        await ebook.download_page(page_num, ebook_dir)
                                    except Exception:
                                        print(f"\n  页面 {page_num + 1} 下载失败: {str(e)}")
                                        continue
                            print(f"  完成 {ebook.page_count} 页下载")
                            downloaded_count += 1
                    except Exception as e:
                        print(f"  电子书下载失败：{filename} - {str(e)}")
                        # 如果电子书下载失败，尝试直接下载原始文件
                        print(f"  尝试直接下载原始文件：{filename}")
                        file_path = os.path.join(download_dir, filename)
                        try:
                            await self.play_api.download_playfile(token, playfile, file_path, mkdir=True)
                            print(f"  原始文件下载完成：{filename}")
                            downloaded_count += 1
                        except Exception as e2:
                            print(f"  原始文件下载也失败：{filename} - {str(e2)}")
                            # 最后尝试直接 HTTP 下载
                            try:
                                if hasattr(playfile, 'url') and playfile.url:
                                    async with self.play_api.session.get(playfile.url) as response:
                                        if response.status == 200:
                                            os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                            with open(file_path, 'wb') as f:
                                                async for chunk in response.content.iter_chunked(8192):
                                                    f.write(chunk)
                                            print(f"  HTTP 直接下载完成：{filename}")
                                            downloaded_count += 1
                                        else:
                                            print(f"  HTTP 错误：{filename} (状态码: {response.status})")
                                else:
                                    print(f"  无可用下载 URL：{filename}")
                            except Exception as e3:
                                print(f"  所有下载方法都失败：{filename} - {str(e3)}")
            
            # 处理可能需要解密的图片文件
            if potentially_scrambled_images:
                print(f"\n处理 {len(potentially_scrambled_images)} 个可能需要解密的图片文件...")
                for file_idx, (filename, playfile) in enumerate(potentially_scrambled_images, 1):
                    print(f"[解密图片 {file_idx}/{len(potentially_scrambled_images)}] 处理：{filename}")
                    self.logger.info(f"尝试解密图片：{filename}")
                    
                    try:
                        # 方法1：尝试使用 PlayAPI 的解密方法
                        decrypt_success = False
                        try:
                            # 创建解密图片目录
                            img_dir = os.path.join(download_dir, "decrypted_images")
                            os.makedirs(img_dir, exist_ok=True)
                            
                            # 尝试使用 PlayAPI 的 download_playfile 方法进行解密下载
                            decrypted_path = os.path.join(img_dir, filename)
                            
                            # 检查 playfile 的类型
                            playfile_type = getattr(playfile, 'type', 'unknown')
                            self.logger.debug(f"{filename} playfile 类型: {playfile_type}")
                            
                            # 使用 download_playfile 方法，它应该能自动处理解密
                            # 添加解密相关参数
                            try:
                                # 尝试带解密参数的下载
                                await self.play_api.download_playfile(token, playfile, decrypted_path, mkdir=True, descramble=True)
                                self.logger.debug(f"使用 descramble=True 下载 {filename}")
                            except TypeError:
                                # 如果不支持 descramble 参数，使用标准方法
                                await self.play_api.download_playfile(token, playfile, decrypted_path, mkdir=True)
                                self.logger.debug(f"使用标准方法下载 {filename}")
                            
                            # 检查文件是否已下载并且有合理大小
                            if os.path.exists(decrypted_path):
                                file_size = os.path.getsize(decrypted_path)
                                self.logger.debug(f"{filename} 下载文件大小: {file_size} bytes")
                                
                                if file_size > 1000:
                                    print(f"  解密下载完成：{filename} ({file_size/1024:.1f}KB)")
                                    downloaded_count += 1
                                    decrypt_success = True
                                else:
                                    raise Exception(f"下载的文件过小: {file_size} bytes")
                            else:
                                raise Exception("文件未创建")
                                
                        except Exception as decrypt_error:
                            self.logger.debug(f"PlayAPI 解密下载失败：{str(decrypt_error)}")
                            
                            # 方法1.5：尝试 EbookSession（作为备用）
                            try:
                                async with EbookSession(self.play_api, tree, playfile) as ebook:
                                    if ebook.page_count > 0:
                                        self.logger.debug(f"将 {filename} 作为单页电子书处理，页数：{ebook.page_count}")
                                        for page_num in range(ebook.page_count):
                                            try:
                                                await ebook.download_page(page_num, img_dir, mkdir=True, force=True)
                                            except TypeError:
                                                await ebook.download_page(page_num, img_dir, mkdir=True)
                                            except Exception:
                                                await ebook.download_page(page_num, img_dir)
                                        print(f"  电子书解密完成：{filename} ({ebook.page_count} 页)")
                                        downloaded_count += 1
                                        decrypt_success = True
                                    else:
                                        raise Exception("页数为0")
                            except Exception as ebook_error:
                                self.logger.debug(f"EbookSession 处理失败：{str(ebook_error)}")
                        
                        # 方法2：如果解密失败，尝试直接下载并提醒用户
                        if not decrypt_success:
                            try:
                                file_path = os.path.join(download_dir, filename)
                                await self.play_api.download_playfile(token, playfile, file_path, mkdir=True)
                                print(f"  原始下载完成：{filename}")
                                print(f"  警告：此图片可能需要手动解密")
                                downloaded_count += 1
                            except Exception as direct_error:
                                self.logger.debug(f"直接下载也失败：{str(direct_error)}")
                                # 方法3：最后尝试 HTTP 下载
                                try:
                                    if hasattr(playfile, 'url') and playfile.url:
                                        async with self.play_api.session.get(playfile.url) as response:
                                            if response.status == 200:
                                                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                                with open(file_path, 'wb') as f:
                                                    async for chunk in response.content.iter_chunked(8192):
                                                        f.write(chunk)
                                                print(f"  HTTP 下载完成：{filename}")
                                                print(f"  警告：此图片可能需要手动解密")
                                                downloaded_count += 1
                                            else:
                                                raise Exception(f"HTTP 状态码: {response.status}")
                                    else:
                                        raise Exception("无可用 URL")
                                except Exception as http_error:
                                    self.logger.error(f"所有下载方法都失败：{str(http_error)}")
                                    raise Exception(f"所有方法都失败: {str(http_error)}")
                            
                    except Exception as e:
                        print(f"  图片处理失败：{filename} - {str(e)}")
                        self.logger.error(f"图片处理失败：{filename} - {str(e)}")
            
            # 处理其他文件（直接下载）
            other_download_files = cpd_files + pdf_files + other_files
            if other_download_files:
                print(f"\n处理 {len(other_download_files)} 个其他文件...")
                for file_idx, (filename, playfile) in enumerate(other_download_files, 1):
                    print(f"[文件 {file_idx}/{len(other_download_files)}] 下载：{filename}")
                    
                    file_path = os.path.join(download_dir, filename)
                    try:
                        # 方法1：尝试使用 PlayAPI 的标准下载方法
                        try:
                            await self.play_api.download_playfile(token, playfile, file_path, mkdir=True)
                            print(f"  标准下载完成：{filename}")
                            downloaded_count += 1
                        except Exception:
                            # 方法2：如果标准方法失败，尝试直接 HTTP 下载
                            if hasattr(playfile, 'url') and playfile.url:
                                async with self.play_api.session.get(playfile.url) as response:
                                    if response.status == 200:
                                        # 确保目录存在
                                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                        with open(file_path, 'wb') as f:
                                            async for chunk in response.content.iter_chunked(8192):
                                                f.write(chunk)
                                        print(f"  直接下载完成：{filename}")
                                        downloaded_count += 1
                                    else:
                                        print(f"  HTTP 错误：{filename} (状态码: {response.status})")
                            else:
                                print(f"  无有效 URL：{filename}")
                    except Exception as e:
                        print(f"  下载失败：{filename} - {str(e)}")
            
            # 显示特殊文件的使用说明
            if cpd_files:
                print("\nCypherGuard for PDF 文件使用说明：")
                print("  1. 下载并安装 CypherGuard for PDF 阅览器")
                print("  2. 使用您的 DLsite 账号登录阅览器")
                print("  3. 在阅览器中打开 .cpd 文件")
            
            print(f"\n下载完成！成功下载 {downloaded_count}/{len(all_files)} 个文件")
            print(f"保存位置：{os.path.abspath(download_dir)}")
            return True
            
        except Exception as e:
            print(f"下载失败：{str(e)}")
            return False
    
    async def run(self):
        """主运行逻辑"""
        try:
            # 登录
            if not await self.login():
                return
            
            # 获取作品列表
            books = await self.get_purchased_books()
            if not books:
                print("无法获取作品列表，程序退出")
                return
            
            # 主循环
            current_page = 1
            while True:
                page_info = self.display_books(page=current_page)
                action_type, value = self.get_user_choice(page_info)
                
                if action_type == "exit":
                    print("感谢使用 DLsite 下载器！")
                    break
                elif action_type == "download":
                    await self.download_work(value)
                    
                    # 询问是否继续
                    continue_choice = input("\n是否继续浏览作品？(y/n)：").strip().lower()
                    if continue_choice not in ['y', 'yes', '是']:
                        print("感谢使用 DLsite 下载器！")
                        break
                elif action_type in ["next_page", "prev_page", "goto_page"]:
                    current_page = value
                    continue  # 直接显示新页面，不询问
                elif action_type == "search":
                    found_count = self.search_works(value)
                    if found_count > 0:
                        print(f"找到 {found_count} 个匹配的作品")
                        current_page = 1  # 重置到第一页
                    else:
                        print("没有找到匹配的作品")
                        self.search_mode = False
                    continue
                elif action_type == "reset_search":
                    self.search_mode = False
                    self.filtered_works = []
                    current_page = 1
                    print("已退出搜索模式")
                    continue
        
        finally:
            # 清理资源
            if self.play_api:
                await self.play_api.close()


async def main():
    """程序入口点"""
    downloader = DLsiteDownloader()
    await downloader.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序已被用户中断")
    except Exception as e:
        print(f"\n程序运行出错：{str(e)}")
        sys.exit(1)
