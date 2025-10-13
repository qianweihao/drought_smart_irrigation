"""土壤特性模型模块"""
import os
import pandas as pd
import numpy as np
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from utils.logger import logger

class SoilProfile:
    """土壤剖面类"""
    def __init__(self, comment=''):
        self.comment = comment
        self.data = None
        self.sdata = None  
        
    def customload(self, data):
        """加载自定义数据"""
        try:
            df = pd.read_csv(data)
            self.sdata = df.set_index('Depth')
            self.data = df
            logger.info(f"已加载土壤数据: {len(self.data)}行")
            
        except Exception as e:
            logger.error(f"加载土壤数据失败: {str(e)}")
            raise
            
    def savefile(self, filename):
        """保存土壤数据到文件"""
        try:
            if self.sdata is not None:
                output = []
                output.append("************************************************************************")
                output.append("pyfao56: FAO-56 Evapotranspiration in Python")
                output.append("Soil Profile Data")
                output.append(f"Timestamp: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                output.append("************************************************************************")
                output.append(f"Comments: {self.comment}")
                output.append("************************************************************************")
                output.append("Depth thetaFC thetaWP  theta0")
                
                for depth, row in self.sdata.iterrows():
                    output.append(f"{depth:>5} {row['thetaFC']:>8.3f} {row['thetaWP']:>8.3f} {row['theta0']:>8.3f}")
                
                with open(filename, 'w') as f:
                    f.write('\n'.join(output))
                logger.info(f"土壤数据已保存到: {filename}")
            else:
                raise ValueError("没有数据可保存")
                
        except Exception as e:
            logger.error(f"保存土壤数据失败: {str(e)}")
            raise

            
    def get_layer_properties(self, depth):
        """获取指定深度的土壤特性"""
        try:
            if self.data is None:
                raise ValueError("未加载土壤数据")
            layer = self.data[self.data['depth'] <= depth].iloc[-1]
            
            return {
                'depth': layer['depth'],
                'texture': layer['texture'],
                'organic_matter': layer['organic_matter'],
                'field_capacity': layer['field_capacity'],
                'wilting_point': layer['wilting_point']
            }
            
        except Exception as e:
            logger.error(f"获取土壤层特性失败: {str(e)}")
            raise 