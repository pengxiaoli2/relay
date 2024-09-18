import subprocess
import re,time
import logging
from rich.logging import RichHandler
import serial
from serial.tools import list_ports
import argparse
import  sys
import os
import datetime
import random
import ctypes

#串口的设置,在测试前需要将串口打开，以便获取到日志
class RelayTool():
    def __init__(self):
        pass
    def list_com_ports(self):
        port_list = list(list_ports.comports())
        port_list_name = []
        if len(port_list) <= 0:
            logging.warning("The Serial port can't find!")
        else:
            for port in port_list:
                port_list_name.append(port.name)
        logging.info(f"Currently COM port:{port_list_name}")
        return port_list_name

    def open_com(self, com_name):
        self.com_name = com_name
        actual_ports = self.list_com_ports()
        if self.com_name not in actual_ports:
            logging.error(f"Currently COM:{com_name}, actuallly com:{actual_ports},Please check your port in local")
            return 1

        try:
            self.open_com = serial.Serial(self.com_name, 9600, timeout=1, write_timeout=1)
            return 0
        except Exception as e:
            logging.error(f"Open com {self.com_name}:9600 failed.", e)
            return 1

    def close_com(self):
        try:
            logging.info(f"Close com {self.com_name}")
            self.open_com.close()
            return 0
        except Exception as e:
            logging.error(f"Close com{self.com_name} failed.{e}")
            return 1

    #继电器一次按键的操作
    def press_power(self, open_time = 0.2):
        #闭合继电器0.2s相当于按power键一次
        self.open_com.write(bytes([0xA0, 0x01, 0x01, 0xA2]))
        time.sleep(open_time)
        #断开继电器
        self.open_com.write(bytes([0xA0, 0x01, 0x00, 0xA1]))
        logging.info(f"Press the power button on the remote control")

    def random_sleep_time(self, max_time, min_time=6):
        random_time = random.uniform(min_time, max_time)
        random_formatted_time = round(random_time, 2)
        logging.info(f"Sleep_time:{random_formatted_time}")
        time.sleep(random_formatted_time)

class FindKeyword(object):
    def __init__(self, log_file_path, standby_keyword, wakeup_keyword):
        self.log_file_path = log_file_path
        self.standby_keyword = standby_keyword
        self.wakeup_keyword = wakeup_keyword

    def keyword_judge(self, pattern):
        # 创建 PowerShell
        if pattern == "standby":
            pattern = self.standby_keyword
        elif pattern == "wakeup":
            pattern = self.wakeup_keyword
        else:
            logging.error("Incorrect pattern. the pattern type can only standby or wakeup")
            return None, ""

        command = (
            f"$logFile = '{self.log_file_path}'; "
            f"$pattern = '{pattern}'; "
            f"$matches = Select-String -Path $logFile -Pattern $pattern; "
            f"if ($matches) {{ $lastMatch = $matches[-1].Line; Write-Output $lastMatch }} "
            f"else {{ Write-Output 'No matching data was found' }}"
        )

        result = subprocess.run(['powershell', '-Command', command], capture_output=True, text=True)
        if result.returncode == 0:
            output = result.stdout.strip()
        else:
            output = result.stderr.strip()
        #logging.debug(output)

        timestamp = re.match(r'\[(.*?)\]', output)
        if timestamp:
            timestamp = timestamp.group(1)
            timestamp = datetime.datetime.strptime(timestamp, "%Y%m%d_%H:%M:%S.%f")
            return timestamp, output
        else:
            output = "The keyword was not obtained or the timestamp of the log should be in the form of [%Y%M%D_%h:%m:%s.%t]"
            #logging.warning(output)
            return None, output

    def compare_keyword_timestamp(self, pattern, last_timestamp, current_timestamp):
        if current_timestamp > last_timestamp:
            return 0
        else:
            logging.debug(f"It's still the same keyword as last time, the {pattern} operation fails this time.")
            return 1
class RelaySerialControl():
    def __init__(self):
        self.parse_args()
        self.init_logging()
        self.print_args()
        self.log_path = self.find_lastest_log_file(self.log_dir)
        self.relay_tool = RelayTool()
        self.find_keyword = FindKeyword(self.log_path, self.standy_keyword, self.wakeup_keyword)

    def parse_args(self):
        """
        argparse.RawTextHelpFormatter控制自动换行
        """
        parser = argparse.ArgumentParser(description='**********Xiaomi project read local serial log  and control usb relay********', prog=sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
        # 添加参数
        parser.add_argument('-r', '--relay', type=str, help='Relay name, ex:-r COM8', required=True)
        parser.add_argument('-p', '--log_dir', type=str, help=r'Serial log dir,ex:-p D:\\log\\Serial-COM7', required=True)
        parser.add_argument('-c', '--circle', type=int, help='The times of script executions, ex:-c 500', required=True)
        parser.add_argument('-s', '--standy_keyword', type=str, help='Keyword of indicating standby completion, ex:-s vdd_cpu_off' , required=True)
        parser.add_argument('-S', '--standy_max', type=int, help='Indicates the maximum waiting time from the completion of standby to wake up(Unit second), ex:-S 30', required=True)
        parser.add_argument('-w', '--wakeup_keyword', type=str, help='Keyword of indicating wakeup completion, ex:-w vdd_cpu_on', required=True)
        parser.add_argument('-W', '--wakeup_max', type=int, help='Indicates the maximum waiting time from the completion of wake up to standyby(Unit second), ex:-W 10', required=True)
        parser.add_argument('-v', '--verbose', action='store_true', help='Show more information while running, default: False')
        # 解析命令行参数
        args = parser.parse_args()
        self.relay = args.relay
        self.log_dir = args.log_dir
        self.circle = args.circle
        self.standy_keyword = args.standy_keyword
        self.standy_max = args.standy_max
        self.wakeup_keyword = args.wakeup_keyword
        self.wakeup_max = args.wakeup_max
        self.verbose = args.verbose
        if not any(vars(args).values()):
            parser.exit(message=parser.format_usage())

    def init_logging(self):
        """ 初始化logging模块(包含动态参数的配置Verbose调试开关) """
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        # 创建Formatter对象
        formatter = logging.Formatter(log_format)

        log_directory = 'console_logs'
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        current_date = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        log_file_path = os.path.join(log_directory, f'console_{current_date}.log')

        handlers = [
            RichHandler(rich_tracebacks=True,  # rich_tracebacks开关
                        tracebacks_show_locals=True,  # Exception时展示代码段
                        log_time_format="[%Y_%m_%d %H:%M:%S]",  # datetime时间格式
                        omit_repeated_times=False,  # False=逐行打印logging时间戳
                        keywords=['error', 'Error', 'Failed', 'Not find the keyword', "Find the keyword", "Sleep_time", "failure", "Run times:"],  # 高亮Console中关键字
                        markup=True),
            logging.FileHandler(filename=log_file_path, mode='w', encoding='utf-8')
        ]

        for handler in handlers:
            handler.setFormatter(formatter)
        # 配置logging
        logging.basicConfig(level=logging.DEBUG if self.verbose else logging.INFO,
                            handlers=handlers)

    def print_args(self):
        """ 打印脚本参数设置情况 """
        args_dict = {
            'Relay': self.relay,
            'Serial log dir': self.log_dir,
            'Circle of stress test': self.circle,
            'Keyword of standy': self.standy_keyword,
            'Maximum duration of standy': self.standy_max,
            'Keyword of wakeup': self.wakeup_keyword,
            'Maximum duration of wakeup': self.wakeup_max,
            'Verbose': self.verbose
        }

        logging.info('Get script parameter configuration:')
        logging.info(f"{'*' * 50}")
        for index, (arg, value) in enumerate(args_dict.items(), 1):
            logging.info(f'[{str(index).zfill(2)}] {arg.ljust(25, " ")} = {value}')
        logging.info(f"{'*' * 50}\n")

    def find_lastest_log_file(self, directory):
        files = os.listdir(directory)
        log_files = [f for f in files if f.endswith('.log')]

        if not log_files:
            return None

        def extract_timestamp(filename):
            try:
                timestamp_str = filename.split('.')[0]
                return timestamp_str
            except IndexError:
                return "00000000-000000"

        latest_file = max(log_files, key=lambda f: extract_timestamp(f))
        latest_file_path = os.path.join(directory, latest_file)
        logging.info(f"log path:{latest_file_path}")
        return latest_file_path

    def execute_operation(self, operation, pattern, max_time, timeout=55):
        success = False
        times = 0
        while True:
            operation()
            self.relay_tool.random_sleep_time(max_time=max_time)
            times += 1

            start_time = time.time()
            #下面的while循环主要是为了适配30次小米电视有一个重启的问题
            while time.time() - start_time < timeout:
                current_timestamp, keyword = self.find_keyword.keyword_judge(pattern=pattern)
                if current_timestamp == None:
                    #如果log里面一直没有关键字，就给current_timestamp赋初始值，防止报错，脚本停止
                    current_timestamp = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
                code = self.find_keyword.compare_keyword_timestamp(pattern, self.last_timestamp, current_timestamp)
                if code == 0:
                    self.last_timestamp = current_timestamp
                    success = True
                    break
                time.sleep(15)

            if current_timestamp == datetime.datetime(1970, 1, 1, 0, 0, 0, 0):
                logging.warning(keyword)
            else:
                logging.info(keyword)

            if success:
                break
            else:
                logging.error(f"Failed to enter {pattern} mode for {times} times")
        return success

    def usb_relay_control_read_keywords(self, relay, circle, stanby_max_time, wakeup_max_time):
        code = self.relay_tool.open_com(relay)
        if code:
            return 1

        #如果日志一直在追加，就会出现将上次执行的结果保存下来，导致判断错误，因此需要获取最后一次待机关键字的那一行
        timestamp, keyword = self.find_keyword.keyword_judge(pattern="standby")
        if timestamp:
           self.last_timestamp =  timestamp
        else:
            self.last_timestamp = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)

        for sleep_time in range(1, circle + 1):
            logging.info(f"Run times: {sleep_time}")

            self.execute_operation(self.relay_tool.press_power,"standby", stanby_max_time)
            self.execute_operation(self.relay_tool.press_power,"wakeup", wakeup_max_time)

        self.relay_tool.close_com()

if __name__ == "__main__":
    relay_serial_control = RelaySerialControl()
    relay_serial_control.usb_relay_control_read_keywords(relay = relay_serial_control.relay,
                                                         circle = relay_serial_control.circle,
                                                         stanby_max_time = relay_serial_control.standy_max,
                                                         wakeup_max_time = relay_serial_control.wakeup_max)
