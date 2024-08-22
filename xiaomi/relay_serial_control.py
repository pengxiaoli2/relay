import time
import serial
from serial.tools import list_ports
import os, datetime
import random
import logging
import argparse
import sys
from rich.logging import RichHandler

#使用说明：https://confluence.amlogic.com/pages/viewpage.action?pageId=433098626
class ComTool():
    _opened_coms = {}
    _com_ports = {}
    _log_filename = {}

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

    def open_com(self, com_names):
        if isinstance(com_names, dict):
            flag = 0
            self._com_ports = com_names
            for serial_type, com_name in com_names.items():
                com_name = com_name.upper()
                log_dir = os.path.abspath('com_logs')
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                open_time = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')

                actual_ports = self.list_com_ports()
                com_exist = False
                for actual_port in actual_ports:
                    if com_name == actual_port:
                        com_exist = True
                        break
                if  com_exist == False:
                    logging.error(f"Currently COM:{com_name}, actuallly com:{actual_ports},Please check your port in local")
                    flag = flag + 1
                try:
                    self._log_filename[com_name] = os.path.join(log_dir, open_time + '_' + com_name + '.log')
                    logging.info("Log will save in " + self._log_filename[com_name])

                    if serial_type == 'relay':
                        com_bps = 9600
                    elif serial_type == 'serial':
                        com_bps = 115200
                    else:
                        logging.error(f"The usb type is not defined")
                        flag = flag + 1
                    logging.info(f"Opening com {com_name}, band rate:{com_bps}...")

                    com = serial.Serial(com_name, com_bps, timeout=1, write_timeout=1)
                    self._opened_coms[com_name] = com
                except Exception as e:
                    logging.error(f"Open com {com_name}:{com_bps} failed.", e)
                    flag = flag + 1
            if flag:
                return 1
            else:
                return 0
        else:
            logging.error("Com_names must be a dict type")
            return 1

    def close_com(self):
        try:
            flag = 0
            for serial_type, com_name in self._com_ports.items():
                logging.info(f"Close com {com_name}")
                self._opened_coms[com_name].close()
        except Exception as e:
            logging.error(f"Close com{com_name} failed.{e}")
            flag += 1
        if flag:
            return 1
        return 0

    def read(self, com_name, print_output=True):
        try:
            readed_bytes = self._opened_coms[com_name].read_all()
            filted_bytes = bytes()
            for i in range(len(readed_bytes)):
                if int(readed_bytes[i]) < 128:
                    filted_bytes += bytes([readed_bytes[i]])
            readed_output = str(filted_bytes, encoding='utf8')
            readed_output = readed_output.replace('\0', '')
            readed_output = readed_output.replace('\r\n', '\n')
            readed_output = readed_output.replace('\x07', '')  #BEL就是\x07，需要删除
            log_filename =  self._log_filename[com_name]
            with open(log_filename, 'a') as log_file:
                if len(readed_output) != 0:
                    log_file.write(readed_output)
            if len(readed_output) != 0 and print_output:
                logging.debug(readed_output)
            return 0, readed_output
        except Exception as e:
            output = f"Read com {self._serial_name} failed."
            logging.error(f"{output}: {e}")
            return 1, output

    def read_more(self, com_name, print_output=True):
        output = ''
        while True:
            code_r, output_r = self.read(com_name = com_name, print_output=False)
            output += output_r
            if code_r != 0:
                if len(output) != 0 and print_output:
                    logging.debug(output)
                return code_r, output
            elif len(output_r) == 0:
                if len(output) != 0 and print_output:
                    logging.debug(output)
                return 0, output

    #设置80秒的延时
    def read_com_keyword(self, com_name, keyword, timeout = 80):
        com_output = ""
        current_time = time.time()
        while time.time() < current_time + timeout:
            time.sleep(0.1)
            code, output = self.read_more(com_name = com_name)
            com_output += output
            if keyword in com_output:
                logging.info(f"Find the keyword:{keyword}")
                return 0, com_output
            if code:
                return 1, com_output

        logging.error(f"Not find the keyword:{keyword}")
        return 2, com_output

    def read_com_duration(self, com_name, duration):
        com_output = ""
        current_time = time.time()
        while time.time() < current_time + duration:
            time.sleep(0.1)
            code, output = self.read_more(com_name = com_name)
            com_output += output
            if code:
                return 1, com_output
        return 0, com_output


    def press_power(self, relay_name, open_time = 0.2):
        #闭合继电器0.2s相当于按power键一次
        self._opened_coms[relay_name].write(bytes([0xA0, 0x01, 0x01, 0xA2]))
        time.sleep(open_time)
        #断开继电器
        self._opened_coms[relay_name].write(bytes([0xA0, 0x01, 0x00, 0xA1]))

    def random_sleep_time(self, min_time, max_time):
        random_time = random.uniform(min_time, max_time)
        random_formatted_time = round(random_time, 2)
        logging.info(f"Sleep_time:{random_formatted_time}")
        return random_formatted_time

class RelaySerialControl():
    def __init__(self):
        self.parse_args()
        self.init_logging()
        self.print_args()
        self.com_tool = ComTool()

    def parse_args(self):
        """
        argparse.RawTextHelpFormatter控制自动换行
        """
        parser = argparse.ArgumentParser(description='**********Xiaomi project read serial log  and control usb relay********', prog=sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
        # 添加参数
        parser.add_argument('-r', '--relay', type=str, help='Relay name, ex:-r COM8', required=True)
        parser.add_argument('-s', '--serial', type=str, help='Serial name,ex:-s COM3', required=True)
        parser.add_argument('-c', '--circle', type=int, help='The times of script executions, ex:-c 500', required=True)
        parser.add_argument('-k', '--standy_keyword', type=str, help='Keyword of indicating standby completion, ex:-k vdd_cpu_off' , required=True)
        parser.add_argument('-a', '--standy_min', type=int, help='Indicates the minimum waiting time from the completion of standby to wake up(unit second), ex:-a 7', required=True)
        parser.add_argument('-b', '--standy_max', type=int, help='Indicates the maximum waiting time from the completion of standby to wake up(Unit second), ex:-b 30', required=True)
        parser.add_argument('-w', '--wakeup_keyword', type=str, help='Keyword of indicating wakeup completion, ex:-w vdd_cpu_on', required=True)
        parser.add_argument('-m', '--wakeup_min', type=int, help='Indicates the minimum waiting time from the completion of wake up to standyby(Unit second), ex:-m 5', required=True)
        parser.add_argument('-n', '--wakeup_max', type=int, help='Indicates the maximum waiting time from the completion of wake up to standyby(Unit second), ex:-n 10', required=True)
        parser.add_argument('-v', '--verbose', action='store_false', help='Show more information while running, default: True')
        # 解析命令行参数
        args = parser.parse_args()
        self.relay = args.relay
        self.serial = args.serial
        self.circle = args.circle
        self.standy_keyword = args.standy_keyword
        self.standy_min = args.standy_min
        self.standy_max = args.standy_max
        self.wakeup_keyword = args.wakeup_keyword
        self.wakeup_min = args.wakeup_min
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
            'Serial': self.serial,
            'Circle of stress test': self.circle,
            'Keyword of standy': self.standy_keyword,
            'Minimum duration of standy': self.standy_min,
            'Maximum duration of standy': self.standy_max,
            'Keyword duration of wakeup': self.wakeup_keyword,
            'Minimum duration of wakeup': self.wakeup_min,
            'Maximum duration of wakeup': self.wakeup_max,
            'Verbose': self.verbose
        }

        logging.info('Get script parameter configuration:')
        logging.info(f"{'*' * 50}")
        for index, (arg, value) in enumerate(args_dict.items(), 1):
            logging.info(f'[{str(index).zfill(2)}] {arg.ljust(25, " ")} = {value}')
        logging.info(f"{'*' * 50}\n")


    def usb_relay_control_read_keywords(self, relay, serial, circle, standby_keyword, stanby_min_time, stanby_max_time, wakeup_keyword, wakeup_min_time, wakeup_max_time):
        com_names = {'relay': relay, 'serial': serial}
        code = self.com_tool.open_com(com_names)
        if code:
            return

        for sleep_time in range(1, circle+1):
            logging.info(f"Run times:{sleep_time}")

            #有的时候待机一次，不生效，设置五次超时
            for stanby_time in range(1, 6):
                #下发待机
                self.com_tool.press_power(relay_name = relay)
                #读待机的关键字
                code, output = self.com_tool.read_com_keyword(com_name = serial, keyword = standby_keyword, timeout=80)
                if code == 0:
                    break
                else:
                    logging.warning(f"{stanby_time} times:Standby failure")
                if stanby_time == 5:
                    logging.error("Failed to enter standby mode for five times")
                    self.com_tool.close_com()
                    return

            duration = self.com_tool.random_sleep_time(min_time = stanby_min_time, max_time = stanby_max_time)
            self.com_tool.read_com_duration(com_name = serial, duration = duration)

            # 有的时候唤醒一次，不生效，设置五次超时
            for wakeup_time in range(1, 6):
                # 下发唤醒
                self.com_tool.press_power(relay_name = relay)
                # 读唤醒的关键字
                code, output = self.com_tool.read_com_keyword(com_name = serial, keyword = wakeup_keyword, timeout=80)
                if code == 0:
                    break
                else:
                    logging.warning(f"{wakeup_time} times, Wake up failure")
                if wakeup_time == 5:
                    logging.error(f"Failed to enter wakeup mode for 5 times")
                    self.com_tool.close_com()
                    return

            # 唤醒成功后需要等待3-10秒
            duration = self.com_tool.random_sleep_time(min_time = wakeup_min_time, max_time = wakeup_max_time)
            self.com_tool.read_com_duration(com_name = serial, duration = duration)

        self.com_tool.close_com()

if __name__ == "__main__":
    #前提条件需要电视现在开机上电状态
    relay_serial_control = RelaySerialControl()
    relay_serial_control.usb_relay_control_read_keywords(relay = relay_serial_control.relay,
                                                         serial=relay_serial_control.serial,
                                                         circle = relay_serial_control.circle,
                                                         standby_keyword = relay_serial_control.standy_keyword,
                                                         stanby_min_time = relay_serial_control.standy_min,
                                                         stanby_max_time = relay_serial_control.standy_max,
                                                         wakeup_keyword = relay_serial_control.wakeup_keyword,
                                                         wakeup_min_time = relay_serial_control.wakeup_min,
                                                         wakeup_max_time = relay_serial_control.wakeup_max)