# -*- coding: utf-8 -*-

'''
    登陆12306，查询、预订车次的Python脚本
    目前只能预订单程车票
    Mac下配合iTerm2使用，可以直接在命令行显示验证码图片

    seat_class_dict index help from: http://www.zpq.me/post/22

    :Author: Ted
    :License: whatever you like
'''

import datetime
import getpass
import os
import re
import requests
import time

from collections import namedtuple, OrderedDict
from itertools import count
from random import randint
from urllib.parse import unquote

from imgcat import imgcat


USERNAME = 'ted-gao@hotmail.com' # 12396.cn 登录账号
START_STATION = '北京' # 出发站，如需手动输入请留空
END_STATION = '上海' # 终点站，如需手动输入请留空

REFRESH_INTERVAL = 5 # 购票自动刷新间隔

Point = namedtuple('Point', ('x', 'y')) # 验证码中的坐标

headers = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
    'Connection': 'keep-alive',
    'Host': 'kyfw.12306.cn',
    'Referer': 'https://kyfw.12306.cn/otn/login/init',
    'UA': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2272.89 Safari/537.36',
}

station_names = {}

seat_class_dict = OrderedDict([
    #       席位名称      json中的index   座次代码
    ('1', ('商务座/特等座',     32,         '9')),
    ('2', ('一等座',           31,         'M')),
    ('3', ('二等座',           30,         'O')),
    ('4', ('高级软卧',         21,         '6')),
    ('5', ('软卧',            23,         '4')),
    ('6', ('动卧',            33,         'F')),
    ('7', ('硬卧',            28,         '3')),
    ('8', ('软座',            24,         '2')),
    ('9', ('硬座',            29,         '1')),
    ('10', ('无座',           26,         '1')),
    ('11', ('其他',           22,         '-')), # 座次代码无法获取，暂时使用‘-’代替
])

is_logged = False

def get_captcha(session, show=True, save=False):
    '''获取验证码'''
    pic_url = 'https://kyfw.12306.cn/passport/captcha/captcha-image?login_site=E&module=login&rand=sjrand'
    captcha = 'captcha.jpg'
    headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
    r = session.get(pic_url, headers=headers)
    raw = r.content
    
    if show:
        imgcat(raw, preserveAspectRatio=True)

    if save:
        with open(captcha, 'wb') as f:
            f.write(raw)

def get_captcha_num():
    '''获取正确图片位置'''
    captcha_pos = input('请输入正确的图片编号(可多选，空格分隔，上排为1、2、3、4，下排为5、6、7、8，回车取消登陆)：')
    if not captcha_pos.strip():
        print('登陆取消')
        print('')
        return
    
    try:
        captcha_num = [int(x) for x in captcha_pos.split()]
        return captcha_num
    except:
        print('格式错误，请重新输入')
        return get_captcha_num()

def compute_captcha_cords(img_number):
    '''将图片的位置编号转成像素点坐标，数据为在一定范围内生成的随机数'''
    row, col = divmod(img_number - 1, 4)

    space = 5 # 两排、四列验证码图片间距
    side_length = 65 # 正方形验证码边长
    offset_x = 5
    offset_y = 10
    margin = 8 # 随机生成坐标时的裕量，即不选取边缘的8个像素

    start = Point(offset_x + side_length * col + space * col,
                  offset_y + side_length * row + space * row)
    x = randint(start.x + margin, start.x + side_length - margin)
    y = randint(start.y + margin, start.y + side_length - margin)
    return Point(x, y)

def cord2str(cord, delimiter=','):
    '''坐标转换成字符串'''
    return str(cord.x) + delimiter + str(cord.y)

def check_captcha(session, answer):
    '''检查是否输入正确的验证码'''
    url = 'https://kyfw.12306.cn/passport/captcha/captcha-check'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    data = {
        'answer': '',
        'login_site': 'E',
        'rand': 'sjrand',
    }
    data['answer'] = answer

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_captcha(session, answer)

def check_login(session, passwd):
    '''登陆请求'''
    url = 'https://kyfw.12306.cn/passport/web/login'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    data = {
        'username': USERNAME,
        'password': passwd,
        'appid': 'otn',
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_login(session, passwd)

def check_uamtk(session):
    url = 'https://kyfw.12306.cn/passport/web/auth/uamtk'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/passport?redirect=/otn/login/userLogin'
    data = {
        'appid': 'otn',
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_uamtk(session)

def check_uamauthclient(session, tk):
    url = 'https://kyfw.12306.cn/otn/uamauthclient'
    headers['Accept'] = '*/*'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/passport?redirect=/otn/login/userLogin'
    headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
    data = {
        'tk': tk,
    }
    
    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_uamauthclient(session, tk)

def login(session):
    '''自定义用于登陆的函数'''
    global is_logged

    try:
        passwd = os.environ['PASSWD']
    except:
        passwd = getpass.getpass('请输入密码(回车取消登陆)：')
    
    if not passwd:
        print('登陆取消')
        return

    captcha_result_code = '4'
    login_result_code = 0
    uamtk_result_code = 0
    uamauth_result_code = 0
    delimiter = ','

    while True:
        get_captcha(s)
        captcha_num = get_captcha_num()

        if captcha_num is None:
            return

        cord_str = [cord2str(compute_captcha_cords(num), delimiter=delimiter) for num in captcha_num]
        answer_str = delimiter.join(cord_str)

        # 逐级检验
        # 首先查验验证码
        captcha_result = check_captcha(s, answer_str)
        # print(captcha_result)
        if captcha_result['result_code'] == captcha_result_code:
            # 验证码通过才会验证用户名、密码
            login_result = check_login(session, passwd)
            # print(login_result)
            if login_result['result_code'] == login_result_code:
                # 如果登陆信息正确
                uamtk_result = check_uamtk(session)
                # print(uamtk_result)
                if uamtk_result['result_code'] == uamtk_result_code:
                    tk = uamtk_result['newapptk']
                    uamauth_result = check_uamauthclient(session, tk)
                    # print(uamauth_result)
                    if uamauth_result['result_code'] == uamauth_result_code:
                        print('登陆成功！')
                        print('')
                        is_logged = True
                        return
                    else:
                        print('登陆失败。。。')
                        print('')
            else: # 否则重新输入
                print('登陆信息不正确，请重新输入')
                print('')
        else: # 否则重新输入
            print('验证码不正确，请重新输入')
            print('')
        
        print('1秒之后重试')
        time.sleep(1)

def get_contacts(session):
    '''获取乘车人信息'''
    url = 'https://kyfw.12306.cn/otn/passengers/query'

    headers['Referer'] = 'https://kyfw.12306.cn/otn/passengers/init'
    data = {
        'pageIndex': 1,
        'pageSize': 10,
    }

    contacts = []
    for i in count(1):
        data['pageIndex'] = i

        try:
            r = session.post(url, headers=headers, data=data)
            result = r.json()['data']['datas']
            if result:
                contacts += result
            else:
                break
        except:
            break
    
    print('')
    print('总共{}位常用联系人'.format(len(contacts)))
    return contacts

def display_contacts(contacts):
    if not contacts:
        print('没有联系人')
        return
    
    formatter = '{:>4}: {:>12} {:>20}'
    for i, contact in enumerate(contacts, 1):
        contact_name = contact.get('passenger_name', '-')
        contact_id = contact.get('passenger_id_no', '-')
        print(formatter.format(i, contact_name, contact_id))

def select_passengers(session):
    contacts = get_contacts(session)
    display_contacts(contacts)

    print('')
    nums = input('请选择乘车人(可多选，空格分隔，回车取消)：')

    if not nums.strip().split():
        return
    else:
        pas_lst = []
        for num in nums.strip().split():
            int_num = int(num) - 1
            if int_num >= 0 and int_num < len(contacts):
                pas_lst.append(contacts[int_num])

    print('已选乘车人为：', '，'.join(i.get('passenger_name') for i in pas_lst))
    return pas_lst

def get_station_names(session):
    '''获取所有车站列表'''
    global station_names
    if not station_names:
        url = 'https://kyfw.12306.cn/otn/resources/js/framework/station_name.js'
        headers['Accept'] = '*/*'
        headers['Referer'] = 'https://kyfw.12306.cn/otn/leftTicket/init'

        try:
            r = session.get(url, headers=headers)
            station_name_str = r.text.split('=')[-1].split(';')[0].strip("'")
            station_names_list = station_name_str.strip('@').split('@')
            station_names = {station.split('|')[1]: tuple(station.split('|')) for station in station_names_list}
        except:
            return get_station_names(session)

def get_station(session, name, msg):
    '''从用户输入获取标准车站名称'''
    get_station_names(session)

    while True:
        station_name = name or input(msg)
        if not station_name in station_names:
            print('该站点不存在，请重新输入')
        else:
            return station_names[station_name][2]

def get_date():
    '''获取乘车日期'''
    travel_date = input('请输入乘车日期(格式为：2000-01-01，回车默认当前日期)：')

    if not travel_date:
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        current_day = now.day

        travel_date = '{year:04d}-{month:02d}-{day:02d}'.format(
            year=current_year, month=current_month, day=current_day)
    return travel_date

def get_train_list(session, start, end, travel_date):
    '''获取车次列表'''
    headers['Referer'] = 'https://kyfw.12306.cn/otn/leftTicket/init'
    params = {
        'leftTicketDTO.train_date': travel_date,
        'leftTicketDTO.from_station': start,
        'leftTicketDTO.to_station': end,
        'purpose_codes': 'ADULT',
    }

    url = 'https://kyfw.12306.cn/otn/leftTicket/queryO'

    try:
        r = session.get(url, headers=headers, params=params)
        return r.json()['data']['result']
    except:
        print('获取车次失败，1秒之后重试')
        time.sleep(1)
        return get_train_list(session, start, end, travel_date)

def get_seat_classes():
    '''让用户输入关注的座次，如只关注高铁二等座'''
    print('')
    print('可选座次如下：')
    for k, v in seat_class_dict.items():
        print('{:>4}: {}'.format(k, v))
    
    seat_classes = input('请选择要查询的座次(可多选，空格分隔，回车默认全选)：').split()
    
    if not seat_classes:
        seat_classes = seat_class_dict.keys()
        return seat_classes
    
    for num in seat_classes:
        if not num in seat_class_dict:
            print('格式错误，请重新选择')
            return get_seat_classes()

    return seat_classes

def display_trains(seat_classes, train_table):
    '''将车次信息输出到命令行'''
    table_header = ['序号', '车次', '出发站', '到达站', '出发时间', '到达时间', '历时']

    seat_class_names = [seat_class_dict[x][0] for x in seat_classes]
    table_header += seat_class_names

    formatter = '\t'.join('{:>4} {:>6} {:>4} {:>4} {:>6} {:>6} {:>6}'.split())
    for _ in seat_class_names:
        formatter += '\t{:>4}'

    print(formatter.format(*table_header))

    for counter, row in enumerate(train_table, 1):
        display_row = [counter, row[3], code2city(row[4]), code2city(row[5]), row[8], row[9], row[10]]
        for x in seat_classes:
            seat_info = row[seat_class_dict[x][1]] or '-'
            display_row.append(seat_info)
        
        print(formatter.format(*display_row))

def select_train_no(train_table):
    '''选择想要购买的车次'''
    while True:
        print('')
        order_str = input('请选择需要购买车次的序号(回车键退出)：')
        if not order_str:
            exit(0)
        else:
            try:
                order = int(order_str)
                break
            except:
                print('')
                print('仅允许输入数字序号，请重新输入')

    if order > len(train_table):
        print('该行不存在，请重新选择')
        return select_train_no(train_table)
    else:
        train_no = train_table[order - 1][3]
        print('所选车次为：', train_no)
        return order - 1, train_no

def get_secret(train_no, train_table):
    '''生成请求用的secret'''
    for row in train_table:
        if train_no in row:
            return unquote(row[0])

    return ''

def check_orderable(train_no, train_table):
    '''检查所选车次是否有余票可下单'''
    for row in train_table:
        if train_no in row:
            return row[0]

    return None

def check_user(session):
    '''验证用户是否登录'''
    url = 'https://kyfw.12306.cn/otn/login/checkUser'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/leftTicket/init'
    data = {
        '_json_att': '',
    }
    
    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_user(session)

def code2city(code):
    '''从车站三位大写字母代码获取车站中文名称'''
    for k, v in station_names.items():
        if code in v:
            return k
    return ''

def submit_order_request(session, secret, start_station, end_station, travel_date):
    '''请求提交订单'''
    url = 'https://kyfw.12306.cn/otn/leftTicket/submitOrderRequest'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/leftTicket/init'
    data = {
        'secretStr': secret,
        'train_date': travel_date,
        'back_train_date': travel_date,
        'tour_flag': 'dc', # 单程
        'purpose_codes': 'ADULT',
        'query_from_station_name': code2city(start_station),
        'query_to_station_name': code2city(end_station),
        'undefined': '',
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return submit_order_request(session)

def get_tokens(session):
    '''获取相关字符串用于后续提交'''
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'

    headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/leftTicket/init'
    data = {
        '_json_att': ''
    }

    try:
        r = session.post(url, headers=headers, data=data)
        response = r.text

        repeat_submit_token = None
        repeat_submit_re = re.compile(r'globalRepeatSubmitToken.*?\'([a-z0-9]+)\';', re.S)
        repeat_submit_lst = repeat_submit_re.findall(response)
        if repeat_submit_lst:
            repeat_submit_token = repeat_submit_lst[0]
        
        train_location = None
        train_loc_re = re.compile(r'train_location\':\'(.*?)\'', re.S)
        train_loc_lst = train_loc_re.findall(response)
        if train_loc_lst:
            train_location = train_loc_lst[0]
        
        train_no = None
        train_no_re = re.compile(r'train_no\':\'(.*?)\'', re.S)
        train_no_lst = train_no_re.findall(response)
        if train_no_lst:
            train_no = train_no_lst[0]
        
        key_check_isChange = None
        key_check_re = re.compile(r'key_check_isChange\':\'(.*?)\'', re.S)
        key_check_isChange_lst = key_check_re.findall(response)
        if key_check_isChange_lst:
            key_check_isChange = key_check_isChange_lst[0]

        left_ticket_str = None
        left_ticket_re = re.compile(r'leftTicketStr\':\'(.*?)\'', re.S)
        left_ticket_lst = left_ticket_re.findall(response)
        if left_ticket_lst:
            left_ticket_str = left_ticket_lst[0]

        return repeat_submit_token, train_location, train_no, key_check_isChange, left_ticket_str
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return get_tokens(session)

def get_passenger_dtos(session, token):
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/getPassengerDTOs'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'
    data = {
        '_json_att': '',
        'REPEAT_SUBMIT_TOKEN': token,
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return get_passenger_dtos(session, token)

def get_passenger_str(passengers, seat_type):
    passenger_ticket_lst = []
    old_passenger_ticket_lst = []
    # 第三位1为成人票，0为学生票
    for passenger in passengers:
        ticket_info = [seat_type, '0', '1', passenger['passenger_name'], passenger['passenger_id_type_code'],
                       passenger['passenger_id_no'], passenger['mobile_no'], 'N']
        passenger_ticket_lst.append(','.join(str(x) for x in ticket_info))

        old_ticket_info = [passenger['passenger_name'], passenger['passenger_id_type_code'],
                           passenger['passenger_id_no'], '1_']
        old_passenger_ticket_lst.append(','.join(str(x) for x in old_ticket_info))
    
    passenger_ticket_str = '_'.join(passenger_ticket_lst)
    old_passenger_str = ''.join(old_passenger_ticket_lst)

    return passenger_ticket_str, old_passenger_str

def check_order_info(session, token, passengers, seat_type):
    '''验证订单信息'''
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/checkOrderInfo'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'
    
    passenger_ticket_str, old_passenger_str = get_passenger_str(passengers, seat_type)

    data = {
        'cancel_flag': '2', # 固定值
        'bed_level_order_num': '000000000000000000000000000000', # 固定值
        'passengerTicketStr': passenger_ticket_str, # 座位类型，0，车票类型，姓名，证件类别，身份证号，电话，N
        'oldPassengerStr': old_passenger_str, # 姓名，证件类别，证件号码，用户类型(passenger_type key in dict)
        'tour_flag': 'dc', # 单程
        'randCode': '', # 固定值
        'whatsSelect': '1', # 固定值
        '_json_att': '', # 固定值
        'REPEAT_SUBMIT_TOKEN': token,
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_order_info(session, token, passengers, seat_type)

def check_queue_count(session, start_station, end_station, travel_date, train_info, seat_type, train_location, train_no, repeat_submit_token, ticket_secret):
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/getQueueCount'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'

    year, month, day = (int(x) for x in travel_date.split('-'))
    weekday = datetime.date(year, month, day).strftime('%a')
    cap_month = datetime.date(year, month, day).strftime('%b')

    date_str_lst = []
    date_str_lst.append(weekday)
    date_str_lst.append(cap_month)
    date_str_lst.append('{:02d}'.format(day))
    date_str_lst.append(str(year))
    date_str_lst.append('00:00:00 GMT+0800 (CST)')
    data = {
        'train_date': ' '.join(date_str_lst),
        'train_no': train_no,
        'stationTrainCode': train_info[3],
        'seatType': seat_type,
        'fromStationTelecode': train_info[6],
        'toStationTelecode': train_info[7],
        'leftTicket': ticket_secret,
        'purpose_codes': '00', # 固定值
        'train_location': train_location,
        '_json_att': '', # 固定值
        'REPEAT_SUBMIT_TOKEN': repeat_submit_token,
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return check_queue_count(session, start_station, end_station, travel_date, train_info, seat_type, train_location, train_no, repeat_submit_token, ticket_secret)

def confirm_single_for_queue(session, train_location, passengers, seat_type, key_check_isChange, repeat_submit_token, ticket_secret):
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/confirmSingleForQueue'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'

    passenger_ticket_str, old_passenger_str = get_passenger_str(passengers, seat_type)

    data = {
        'passengerTicketStr': passenger_ticket_str,
        'oldPassengerStr': old_passenger_str,
        'randCode': '',
        'purpose_codes': '00',
        'key_check_isChange': key_check_isChange,
        'leftTicketStr': ticket_secret,
        'train_location': train_location,
        'choose_seats': '',
        'seatDetailType': '000',
        'whatsSelect': '1',
        'roomType': '00',
        'dwAll': 'N',
        '_json_att': '',
        'REPEAT_SUBMIT_TOKEN': repeat_submit_token,
    }

    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return confirm_single_for_queue(session, train_location, passengers, seat_type, key_check_isChange, repeat_submit_token, ticket_secret)

def result_order_for_dc_queue(session, order_no, repeat_submit_token):
    url = 'https://kyfw.12306.cn/otn/confirmPassenger/resultOrderForDcQueue'
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['Referer'] = 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'
    data = {
        'orderSequence_no': order_no,
        '_json_att': '',
        'REPEAT_SUBMIT_TOKEN': repeat_submit_token,
    }
    
    try:
        r = session.post(url, headers=headers, data=data)
        return r.json()
    except:
        print('请求失败，1秒之后重试')
        time.sleep(1)
        return result_order_for_dc_queue(session, order_no, repeat_submit_token)

def place_order(session, start_station, end_station, travel_date, train_info, passengers, seat_type, secret, left_ticket_secret):
    '''下单'''
    if not is_logged:
        login(session)

    # 进入订单页面
    user_check_result = check_user(session)
    # print(user_check_result)
    
    submit_result = submit_order_request(session, secret, start_station, end_station, travel_date)
    # print(submit_result)

    repeat_submit_token, train_location, train_no, key_check_isChange, left_ticket_str = get_tokens(session)

    passenger_dtos_result = get_passenger_dtos(session, repeat_submit_token)
    # print(passenger_dtos_result)
    # 离开订单页面

    # 开始检查订单
    order_info = check_order_info(session, repeat_submit_token, passengers, seat_type)
    # print(order_info)

    queue_count = check_queue_count(session, start_station, end_station, travel_date, train_info, seat_type, train_location, train_no, repeat_submit_token, left_ticket_str)
    # print(queue_count)
    # 结束检查订单

    # 开始提交订单
    single_queue = confirm_single_for_queue(session, train_location, passengers, seat_type, key_check_isChange, repeat_submit_token, left_ticket_str)
    # print(single_queue)

    result_order = result_order_for_dc_queue(session, '', repeat_submit_token)
    # print(result_order)
    # 结束提交订单
    
    try:
        success = result_order['status']
        error_msg = result_order['data']['errMsg']
        if success:
            return True, ''
        else:
            return False, error_msg
    except:
        return False, '未知错误'

def display_avail_seats(train_info):
    # print(train_info)
    print('可选座次如下：')
    for k, v in seat_class_dict.items():
        will_print = False
        field = train_info[v[1]]
        try:
            ticket_count = int(field)
            will_print = True
        except:
            if field == '有':
                will_print = True
        if will_print:
            print('{:>4} {:>12} {:>10}'.format(k, v[0], field))
    
def choose_seat(train_info):
    display_avail_seats(train_info)

    print('')
    selected_seat = input('请选择欲购买座次(单选，回车重新选择车次)：')
    if not selected_seat:
        return None
    else:
        return selected_seat.strip().split()[0]

def search_ticket(session, travel_date=None, passengers=None):
    '''查询车次'''
    start_station = get_station(session, START_STATION, '请输入起始站(如：北京)：')
    end_station = get_station(session, END_STATION, '请输入终点站(如：上海)：')

    if not travel_date:
        travel_date = get_date()

    seat_classes = get_seat_classes()

    train_list = get_train_list(session, start_station, end_station, travel_date)
    train_table = [tuple(x.split('|')) for x in train_list]

    display_trains(seat_classes, train_table)

    row, train_no = select_train_no(train_table)
    secret = get_secret(train_no, train_table)

    left_ticket_secret = check_orderable(train_no, train_table)

    if left_ticket_secret:
        seat_type = ''
        seat_class = choose_seat(train_table[row])
        if not seat_class:
            return search_ticket(session, travel_date, passengers)
        seat_type = seat_class_dict[seat_class][2]
        success, msg = place_order(session, start_station, end_station, travel_date, train_table[row], passengers, seat_type, secret, left_ticket_secret)
    else:
        refresh = input('该车次无余票，是否自动刷新购买？回车键取消，其他键继续：') # 输入其他命令重新查询
        if not refresh:
            return
        else:
            while not left_ticket_secret:
                print('*' * 10, datetime.datetime.now(), '*' * 10)
                train_list = get_train_list(session, start_station, end_station, travel_date)
                train_table = [tuple(x.split('|')) for x in train_list]

                display_trains(seat_classes, train_table)
                time.sleep(randint(int(REFRESH_INTERVAL - REFRESH_INTERVAL / 3),
                                   int(REFRESH_INTERVAL + REFRESH_INTERVAL / 3)))
                left_ticket_secret = check_orderable(train_no, train_table)

            success, msg = place_order(session, start_station, end_station, travel_date, train_table[row], passengers, seat_type, secret, left_ticket_secret)
    
    if success:
        print('订单已经生成，请尽快付款，否则将会被取消')
    else:
        print('订票失败，{}，自动重试'.format(msg))
        return search_ticket(session, travel_date=travel_date)


if __name__ == '__main__':
    s = requests.session()
    login(s)
    passengers = select_passengers(s)
    search_ticket(s, passengers=passengers)
