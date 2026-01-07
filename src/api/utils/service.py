import json
import os
from datetime import datetime
from .utils import get_machine_id, verify_license, format_timestamp, calculate_remaining_days

# 授权信息存储文件路径
LICENSE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'license.json')

# 确保data目录存在
os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)


class LicenseService:
    """授权服务类"""
    
    def __init__(self):
        self.license_data = None
        self.load_license()
    
    def load_license(self):
        """从文件加载授权信息"""
        try:
            if os.path.exists(LICENSE_FILE):
                with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                    self.license_data = json.load(f)
        except Exception as e:
            print(f"加载授权信息失败: {e}")
            self.license_data = None
    
    def save_license(self, license_code, license_info):
        """保存授权信息到文件"""
        try:
            data = {
                'license_code': license_code,
                'machine_id': license_info['machine_id'],
                'start': license_info['start'],
                'end': license_info['end'],
                'activated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.license_data = data
            return True
        except Exception as e:
            print(f"保存授权信息失败: {e}")
            return False
    
    def get_machine_id(self):
        """获取当前机器ID"""
        return get_machine_id()
    
    def get_license_status(self):
        """
        获取授权状态
        :return: 授权状态字典
        """
        machine_id = self.get_machine_id()
        
        # 如果没有授权信息
        if not self.license_data:
            return {
                'is_licensed': False,
                'status': 'not_licensed',
                'machine_id': machine_id,
                'message': '未授权'
            }
        
        # 验证授权码
        license_code = self.license_data.get('license_code')
        is_valid, result = verify_license(license_code, machine_id)
        
        if not is_valid:
            return {
                'is_licensed': False,
                'status': 'invalid',
                'machine_id': machine_id,
                'message': result
            }
        
        # 授权有效
        start_time = result['start']
        end_time = result['end']
        remaining_days = calculate_remaining_days(end_time)
        
        # 判断状态
        current_time = datetime.now().timestamp()
        if current_time > end_time:
            status = 'expired'
        elif remaining_days <= 7:
            status = 'expiring_soon'
        else:
            status = 'active'
        
        return {
            'is_licensed': True,
            'status': status,
            'machine_id': machine_id,
            'start_time': format_timestamp(start_time),
            'end_time': format_timestamp(end_time),
            'remaining_days': remaining_days,
            'activated_at': self.license_data.get('activated_at')
        }
    
    def activate_license(self, license_code):
        """
        激活授权码
        :param license_code: 授权码字符串
        :return: (是否成功, 结果信息)
        """
        machine_id = self.get_machine_id()
        
        # 验证授权码
        is_valid, result = verify_license(license_code, machine_id)
        
        if not is_valid:
            return False, result
        
        # 保存授权信息
        if self.save_license(license_code, result):
            return True, self.get_license_status()
        else:
            return False, "保存授权信息失败"
    
    def is_licensed(self):
        """
        快速检查是否已授权（用于拦截器）
        :return: bool
        """
        status = self.get_license_status()
        return status['is_licensed'] and status['status'] in ['active', 'expiring_soon']


# 创建全局单例
license_service = LicenseService()