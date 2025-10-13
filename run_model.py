
import os
import sys
from datetime import datetime

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.append(project_root)

from src.aquacrop.aquacrop_modeling import analyze_growth_stages, run_model_and_save_results, get_growth_stages_from_model
from src.utils.logger import logger

def main():
    """运行AquaCrop模型,更新生育期数据"""
    logger.info("=" * 50)
    logger.info(f"开始运行AquaCrop模型更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    try:
        os.makedirs(os.path.join(project_root, 'data/model_output'), exist_ok=True)
        
        results = run_model_and_save_results()
        
        if results and "stage_results" in results and results["stage_results"]:
            stages = results["stage_results"]
            logger.info("\n生育期数据验证:")
            
            is_continuous = True
            for i in range(1, len(stages)):
                prev_end_date = stages[i-1]["结束日期"]
                curr_start_date = stages[i]["开始日期"]
                
                if isinstance(prev_end_date, str):
                    prev_end_date = datetime.strptime(prev_end_date, "%Y-%m-%d").date()
                    
                if isinstance(curr_start_date, str):
                    curr_start_date = datetime.strptime(curr_start_date, "%Y-%m-%d").date()
                
                days_diff = (curr_start_date - prev_end_date).days
                
                if days_diff != 1:
                    is_continuous = False
                    logger.warning(f"  错误: {stages[i-1]['阶段']}结束于{prev_end_date}，但{stages[i]['阶段']}开始于{curr_start_date}")
                    logger.warning(f"  间隔: {days_diff}天")
            
            if is_continuous:
                logger.info("  所有生育期日期已验证连续，每个阶段的开始日期都是上一个阶段结束日期的下一天")
                logger.info(f"  总生育期: 从{stages[0]['开始日期']}到{stages[-1]['结束日期']}")
            else:
                logger.warning("  警告: 发现生育期日期不连续，请检查")
        else:
            logger.warning("未能生成有效的生育期数据")
            
        logger.info("\n模型运行及数据更新完成!")
        
        return 0
    except Exception as e:
        logger.error(f"运行AquaCrop模型时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("开始重新生成小麦生育期数据...")
    logger.info("此过程将确保生育期数据完全连续，即每个阶段的开始日期是上一阶段的结束日期的下一天")
    logger.info("=" * 80)
    
    exit_code = main()
    
    if exit_code == 0:
        logger.info("\n生育期数据生成成功! 您可以通过以下方式查看更新后的数据:")
        logger.info("1. 访问仪表盘页面: http://localhost:5000/dashboard")
        logger.info("2. 查看生育期CSV文件: src/aquacrop/wheat_growth_stages.csv")
        logger.info("=" * 80)
    else:
        logger.error("\n生育期数据生成失败,请查看日志获取更多信息")
        logger.error("=" * 80)
        
    sys.exit(exit_code) 