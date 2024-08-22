from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.proto import rfc1902
import logging
import time
import random
import subprocess
import os, sys
import argparse
from rich.logging import RichHandler


#使用说明：https://confluence.amlogic.com/pages/viewpage.action?pageId=402528418

"""继电器的网段是固定的192.168.0.100"""
class WebPowerSwitch(object):
    def __init__(self, device_ip):
        self.device_ip = device_ip
        self.user_account = 'admin'
        self.user_pwd = '1234'

    def power_control(self, device_port, status):
        logging.info(f'WebPowerSwitch power {status.lower()}, device port:{device_port}')
        status = status.upper()
        if os.name == 'posix':
            power_cmd = ('curl http://%s:%s@%s/outlet?%s=%s >/dev/null 2>&1' % (
                self.user_account, self.user_pwd, self.device_ip, device_port, status))
        else:
            power_cmd = ('curl http://%s:%s@%s/outlet?%s=%s >nul' % (
                self.user_account, self.user_pwd, self.device_ip, device_port, status))
        logging.debug(f"WebPowerSwitch relay power cmd:{power_cmd}")

        try:
            process = subprocess.Popen(power_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell =True)
            out,err = process.communicate(4)
            logging.debug(f"{out.decode()}, return code:{process.poll()}")
            if process.poll() != 0:
                logging.error(f"{err.decode()}")
                sys.exit(1)
        except Exception as e:
            logging.error(f"Subprocess.Popen error:{e}")
            sys.exit(1)

class GWGJ(object):
    def __init__(self, device_ip):   #这个是别人写的固定的用法，device_number选择的哪个口
        self.device_ip = device_ip
        try:
            self.cmdg = cmdgen.CommandGenerator(None)
        except Exception as e:
            logging.error(f'Create CommandGenerator Failed: {e}')

    def power_control(self, device_port, status):
        logging.info(f'GWGJ power {status.lower()}, device port:{device_port}')
        status = 1 if status.lower() == "on" else (2 if status.lower() == "off" else print("status must be on or off") or None)
        self.sOId = '.1.3.6.1.4.1.23280.9.1.2.%d' % int(device_port)
        try:
            errorIndication, errorStatus, errorIndex, varBinds = self.cmdg.setCmd(
                cmdgen.CommunityData('pudinfo', 'private', 0),
                cmdgen.UdpTransportTarget((self.device_ip, 161)),
                (self.sOId, rfc1902.Integer(status)))
            if errorIndication or errorStatus:
                logging.error(f'Cmdg.setCmd error: errorIndication:{errorIndication}, {errorStatus.prettyPrint()}' 
                              f'at {errorIndex}')
                sys.exit(1)
        except Exception as e:
            logging.error(f'Cmdg.setCmd error: {e}')
            sys.exit(1)

class RelayPower(object):
    def __init__(self):
        self.parse_args()
        self.init_logging()
        self.print_args()

        try:
            process = subprocess.run(['ping', '-n', '5', self.ip], capture_output=True, text=True, check=True)
        except Exception as e:
            logging.error(f"Failed to ping device ip {self.ip}")
            sys.exit(1)

        if (int(self.mode) == 1 and self.range is not None) or (int(self.mode) == 2 and self.time is not None):
            logging.info(f"Usage error. For correct  example: (-m 1 -t 50) or (-m 2 -r 50,55)")
            sys.exit(1)

        if int(self.device) == 1:
            self.relay = GWGJ(self.ip)
        elif int(self.device) == 2:
            self.relay = WebPowerSwitch(self.ip)
    #需要研究下
    @staticmethod
    def time_range(value):
        # 解析范围参数，并返回一个元组
        min_value, max_value = map(int, value.split(','))
        return min_value, max_value

    def print_args(self):
        """ 打印脚本参数设置情况 """
        args_dict = {
            'Device': self.device,
            'IP': self.ip,
            'Port': self.port,
            'Mode of power on': self.mode,
            'Fixde time of power on': self.time,
            'Random time of power on': self.range,
            'Circle of stress test': self.circle,
            'Duration of stress test': self.duration,
            'Verbose': self.verbose
        }

        logging.info('Get relay control parameter configuration:')
        logging.info(f"{'*' * 50}")
        for index, (arg, value) in enumerate(args_dict.items(), 1):
            logging.info(f'[{str(index).zfill(2)}] {arg.ljust(16, " ")} = {value}')
        logging.info(f"{'*' * 50}\n")

    def parse_args(self):
        """
        argparse.RawTextHelpFormatter控制自动换行
        """
        parser = argparse.ArgumentParser(description='**********relay power********', prog=sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
        # 添加参数
        parser.add_argument('-d', '--device', type=str, help='Type of device,1:GWGJ,2:WebPowerSwitch, ex:-d 1', required=True)
        parser.add_argument('-i', '--ip', type=str, help='Ip address of the device,ex:-i 192.168.0.100', required=True)
        parser.add_argument('-p', '--port', type=int, help='Port of the device,GWGJ:2 ports,WebPowerSwitch:8 ports, ex:-p 1' , required=True)
        parser.add_argument('-m', '--mode', type=int, help='''Duration of power on
            mode=1: fixed duration(use with -t time, ex:-m 1 -t 60), power off 5s
            mode=2: random duration(use with -r range, ex:-m 2 -r 50,60), power off 5s''', required=True)
        #parser.add_mutually_exclusive_group是互斥组，表明必须输入-t和-m中的一个参数
        group1 = parser.add_mutually_exclusive_group(required=True)
        group1.add_argument('-t', '--time', type=int, help='Fixed duration of power on(unit:seconds),ex:-t 60')
        group1.add_argument('-r', '--range', type=str, help='Random duration of power on(unit:seconds), ex:-r 50,60')
        # parser.add_mutually_exclusive_group是互斥组，表明必须输入-c和-D中的一个参数
        group2 = parser.add_mutually_exclusive_group(required=True)
        group2.add_argument('-c', '--circle', type=int, help='The times of script executions, ex:-c 5000')
        group2.add_argument('-D', '--duration', type=float, help='The duration of script executions((unit:hours)), ex:-D 48')
        parser.add_argument('-v', '--verbose', action='store_true', help='Show more information while running, default: False')
        # 解析命令行参数
        args = parser.parse_args()

        self.device = args.device
        self.ip = args.ip
        self.port = args.port
        self.mode = args.mode
        self.time = args.time
        #如果没有判断，当args.range为空的时候会报错，TypeError: cannot unpack non-iterable NoneType object
        self.range = args.range
        self.circle = args.circle
        self.duration = args.duration
        self.verbose = args.verbose
        if not any(vars(args).values()):
            parser.exit(message=parser.format_usage())

    def init_logging(self):
        """ 初始化logging模块(包含动态参数的配置Verbose调试开关) """
        logging.basicConfig(level=logging.DEBUG if self.verbose else logging.INFO,
                            format='%(message)s',
                            handlers=[
                                RichHandler(rich_tracebacks=True,  # rich_tracebacks开关
                                            tracebacks_show_locals=True,  # Exception时展示代码段
                                            log_time_format="[%Y/%m/%d %H:%M:%S]",  # datetime时间格式
                                            omit_repeated_times=False,  # False=逐行打印logging时间戳
                                            keywords=['error', 'Error', 'Failed']),  # 高亮Console中关键字
                                logging.FileHandler('Script.log', mode='w', encoding='utf-8')
                            ])

    def stress_mode_control(self, circle, duration, mode, fixed_time, range_time, poweroff_time=5):
        if circle is not None:
            logging.info(f"The script stress test for a total of {circle} times")
            logging.info(f"Fixed duration of power on:{fixed_time}s, power off:{poweroff_time}s") if mode == 1 else \
                (logging.info(f"Random duration of power on:({range_time})s, power off:{poweroff_time}s"))

            times = 0
            while times < circle:
                self.power_mode_control(mode, fixed_time, range_time, poweroff_time)
                times += 1
                logging.info(f"The {times} times stress test was completed")
        elif duration is not None:
            logging.info(f"The script stress test for a total of {duration} hours")
            logging.info(f"Fixed duration of power on:{fixed_time}s, power off:{poweroff_time}s") if mode == 1 else \
                (logging.info(f"Random duration of power on:({range_time})s, power off:{poweroff_time}s"))
            start_time = time.time()
            while time.time() - start_time < duration * 3600:
                self.power_mode_control(mode, fixed_time, range_time, poweroff_time)
                logging.info(f"The {time.time() - start_time} seconds stress test was completed")

    def power_mode_control(self, mode, fixed_time, range_time, poweroff_time):
        if range_time is not None:
            min, max = self.time_range(range_time)
        poweron_duration = fixed_time if mode == 1 else random.uniform(min, max)
        self.relay.power_control(device_port = self.port, status = "on")
        logging.debug(f"Duration of Power on:{poweron_duration}s")
        time.sleep(poweron_duration)
        self.relay.power_control(device_port = self.port, status = "off")
        time.sleep(poweroff_time)

if __name__ == "__main__":
    relayPower = RelayPower()
    relayPower.stress_mode_control(
        circle = relayPower.circle,   #running circle.ex:-c 5000
        duration = relayPower.duration, #running duration.ex:-D 48
        mode = relayPower.mode,     #mode of power on.ex -m 1
        fixed_time= relayPower.time,     #fixed duration of power on.ex -m 1 -t 50
        range_time = relayPower.range)    #random duration of power on.ex -m 2 -r 50,55


