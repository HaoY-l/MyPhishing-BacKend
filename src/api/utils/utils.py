import json
import base64
import uuid
import platform
from datetime import datetime
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA

# 公钥字符串 - 你需要替换成你自己的公钥
PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqlSRT42ct7kuTo5HdHDS
UU7MnRKxJCCyJzLbxd0S+v3vwUZ91t1CPmRh4OJHxe/DE9XxIS83BG4wjLzlgvfp
Um2aUhicTFypOl9ACqbXIjFueUoRTpY7WzJHe99RgGNYbw+TbcQLHM0KSUKaejdN
JsxAsSVqLKOWVgrViw6meD6Yun310K0MOywWAKcRIxYiPnJ+i0ynKPLPC5FQBtLF
239JtSNz32cNJi7Q+uxH28QkkcH5rG1JmGCo7OprQHpPCV7GeapClkBva2mCgnvm
qmaIB/e1KiudH2W+UweSoEOzMsLN6M8vBcJxIfMz65iysDMMLsf+bauJGnqipprB
bwIDAQAB
-----END PUBLIC KEY-----"""


def get_machine_id():
    """
    获取机器唯一标识(MAC地址)
    :return: 格式化的MAC地址字符串
    """
    try:
        # 获取MAC地址
        mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
        # 格式化为 aa:bb:cc:dd:ee:ff
        mac_formatted = ':'.join([mac[i:i+2] for i in range(0, 12, 2)])
        return mac_formatted
    except Exception as e:
        # 降级方案：使用主机名+平台信息生成唯一标识
        fallback = f"{platform.node()}_{platform.system()}_{platform.machine()}"
        return fallback


def verify_license(license_code, current_machine_id):
    """
    验证授权码
    :param license_code: 授权码字符串
    :param current_machine_id: 当前机器ID
    :return: (是否有效, 授权数据或错误信息)
    """
    try:
        # 第一步：Base64解码授权码
        license_json = base64.b64decode(license_code).decode()
        license_obj = json.loads(license_json)
        
        # 检查必要字段
        if 'data' not in license_obj or 'signature' not in license_obj:
            return False, "授权码格式错误：缺少必要字段"
        
        # 第二步：解码数据和签名
        data_encoded = license_obj['data']
        signature_encoded = license_obj['signature']
        
        data_json = base64.b64decode(data_encoded)
        signature = base64.b64decode(signature_encoded)
        
        # 第三步：验证签名
        try:
            public_key = RSA.import_key(PUBLIC_KEY)
            h = SHA256.new(data_json)
            pkcs1_15.new(public_key).verify(h, signature)
        except (ValueError, TypeError) as e:
            return False, "授权码签名验证失败：授权码无效或已被篡改"
        
        # 第四步：解析授权数据
        data = json.loads(data_json)
        
        # 检查必要字段
        required_fields = ['machine_id', 'start', 'end']
        for field in required_fields:
            if field not in data:
                return False, f"授权数据格式错误：缺少{field}字段"
        
        # 第五步：验证机器ID
        if data['machine_id'] != current_machine_id:
            return False, f"机器码不匹配：此授权码仅适用于机器 {data['machine_id']}"
        
        # 第六步：验证时间
        current_time = int(datetime.now().timestamp())
        start_time = data['start']
        end_time = data['end']
        
        if current_time < start_time:
            start_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
            return False, f"授权未生效：将于 {start_str} 生效"
        
        if current_time > end_time:
            end_str = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
            return False, f"授权已过期：于 {end_str} 过期"
        
        # 验证成功，返回授权数据
        return True, data
        
    except base64.binascii.Error:
        return False, "授权码格式错误：Base64解码失败"
    except json.JSONDecodeError:
        return False, "授权码格式错误：JSON解析失败"
    except Exception as e:
        return False, f"授权码验证失败：{str(e)}"


def format_timestamp(timestamp):
    """格式化时间戳为可读时间"""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def calculate_remaining_days(end_timestamp):
    """计算剩余天数"""
    current_time = datetime.now().timestamp()
    remaining_seconds = end_timestamp - current_time
    return max(0, int(remaining_seconds / 86400))  # 86400秒 = 1天