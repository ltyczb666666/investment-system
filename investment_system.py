import os
import json
import shutil
import uuid
import re
import tempfile
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

import gradio as gr
from sqlalchemy import create_engine, Column, String, Text, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

# ====================== 1. 基础配置 ======================
TOOL_NAME = "旅投银创投资业务团队全流程库"
PROJECT_STAGES = [
    "储备项目", "拟推进项目", "立项阶段", "已开展商务尽调项目",
    "初审阶段", "尽职调查阶段", "决策阶段", "投后管理阶段",
    "项目业绩回溯", "投资退出阶段"
]

def get_base_dir():
    """智能选择可用的存储目录"""
    candidates = [
        Path("D:/lvtou_investment_data"),
        Path("E:/lvtou_investment_data"),
        Path.home() / "lvtou_investment_data",
        Path(tempfile.gettempdir()) / "lvtou_investment_data"
    ]
    
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.touch()
            test_file.unlink()
            print(f"✅ 数据目录已选择: {path}")
            return path
        except:
            continue
    
    fallback = Path.home() / "lvtou_investment_data"
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"⚠️ 使用默认目录: {fallback}")
    return fallback

BASE_DIR = get_base_dir()
FILE_STORAGE_DIR = BASE_DIR / "uploaded_files"
DB_PATH = BASE_DIR / "investment_db.sqlite"

FILE_STORAGE_DIR.mkdir(exist_ok=True)
for stage in PROJECT_STAGES:
    (FILE_STORAGE_DIR / stage).mkdir(exist_ok=True)

# ====================== 2. 数据库模型 ======================
Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False)
    stage = Column(String(64), nullable=False)
    project_type = Column(String(128))
    industry = Column(String(128))
    industry_code = Column(String(64))
    financial_data = Column(Text)
    team = Column(Text)
    business_model = Column(Text)
    core_resource = Column(Text)
    market_share = Column(Text)
    business_outlook = Column(Text)
    other_info = Column(Text)
    remark = Column(Text)
    marked = Column(String(16), default="normal")
    files = Column(JSON, default=list)
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ====================== 3. 数据库连接 ======================
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30}
)
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

@contextmanager
def get_db():
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ====================== 4. 文件管理 ======================
def sanitize_filename(filename):
    """清理文件名，保留中文和常用字符"""
    if not filename:
        return "unnamed_file.bin"
    name, ext = os.path.splitext(filename)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff\-_. ]', '', name)
    safe_ext = re.sub(r'[^\w.]', '', ext)
    if not safe_name:
        safe_name = "unnamed_file"
    if not safe_ext:
        safe_ext = ".bin"
    return f"{safe_name}{safe_ext}"

def save_uploaded_file(file, stage, project_id):
    """保存上传的文件"""
    if not file:
        return None
    try:
        relative_dir = f"{stage}/{project_id}"
        abs_dir = FILE_STORAGE_DIR / relative_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if hasattr(file, 'name'):
            orig_name = Path(file.name).name
        else:
            orig_name = "uploaded_file"
        
        safe_name = sanitize_filename(orig_name)
        file_name = f"{timestamp}_{safe_name}"
        abs_path = abs_dir / file_name
        shutil.copy2(file.name, abs_path)
        return f"{relative_dir}/{file_name}"
    except Exception as e:
        print(f"保存文件失败: {e}")
        return None

def get_file_objects(file_paths):
    """获取文件对象列表"""
    if not file_paths:
        return []
    file_objects = []
    for rel_path in file_paths:
        abs_path = FILE_STORAGE_DIR / rel_path
        if abs_path.exists():
            file_objects.append(abs_path)
    return file_objects

def delete_project_files(project):
    """删除项目关联的所有文件"""
    if not project.files:
        return
    for rel_path in project.files:
        abs_path = FILE_STORAGE_DIR / rel_path
        try:
            if abs_path.exists():
                os.remove(abs_path)
        except:
            pass
    project_dir = FILE_STORAGE_DIR / project.stage / project.id
    try:
        if project_dir.exists():
            shutil.rmtree(project_dir)
    except:
        pass

# ====================== 5. 项目管理器 ======================
class ProjectManager:
    @staticmethod
    def generate_project_id():
        """生成唯一项目ID"""
        return f"proj_{uuid.uuid4().hex[:8]}"
    
    def add_project(self, stage, project_data, remark, marked, files):
        """新增项目"""
        try:
            project_name = project_data.get("项目名称", "")
            if not project_name:
                return "❌ 新增失败：项目名称不能为空"
            
            with get_db() as db:
                project_id = self.generate_project_id()
                project = Project(
                    id=project_id,
                    name=project_name,
                    stage=stage,
                    project_type=project_data.get("项目类型", ""),
                    industry=project_data.get("所属行业", ""),
                    industry_code=project_data.get("所属行业代码", ""),
                    financial_data=project_data.get("项目核心财务数据", ""),
                    team=project_data.get("项目团队", ""),
                    business_model=project_data.get("商业模式", ""),
                    core_resource=project_data.get("核心竞争资源", ""),
                    market_share=project_data.get("市场占有率", ""),
                    business_outlook=project_data.get("商业展望", ""),
                    other_info=project_data.get("其他", ""),
                    remark=remark,
                    marked=marked
                )
                
                file_paths = []
                if files:
                    for file in files:
                        if file is not None:
                            file_path = save_uploaded_file(file, stage, project_id)
                            if file_path:
                                file_paths.append(file_path)
                project.files = file_paths
                db.add(project)
            
            return f"✅ 项目「{project_name}」新增成功！ID：{project_id}"
        except Exception as e:
            return f"❌ 新增失败：{str(e)}"
    
    def delete_project(self, project_id):
        """删除项目"""
        try:
            with get_db() as db:
                project = db.query(Project).filter(Project.id == project_id).first()
                if not project:
                    return "❌ 项目不存在"
                project_name = project.name
                delete_project_files(project)
                db.delete(project)
            return f"✅ 项目「{project_name}」已删除！"
        except Exception as e:
            return f"❌ 删除失败：{str(e)}"
    
    def update_project_stage(self, project_id, new_stage):
        """更新项目阶段"""
        try:
            with get_db() as db:
                project = db.query(Project).filter(Project.id == project_id).first()
                if not project:
                    return "❌ 项目不存在"
                old_stage = project.stage
                project.stage = new_stage
                
                if project.files:
                    new_file_paths = []
                    for rel_path in project.files:
                        old_abs_path = FILE_STORAGE_DIR / rel_path
                        if old_abs_path.exists():
                            file_name = Path(rel_path).name
                            new_rel_path = f"{new_stage}/{project_id}/{file_name}"
                            new_abs_path = FILE_STORAGE_DIR / new_rel_path
                            new_abs_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(old_abs_path), str(new_abs_path))
                            new_file_paths.append(new_rel_path)
                    project.files = new_file_paths
                
                old_dir = FILE_STORAGE_DIR / old_stage / project_id
                try:
                    if old_dir.exists() and not any(old_dir.iterdir()):
                        old_dir.rmdir()
                except:
                    pass
            return f"✅ 项目已从「{old_stage}」移至「{new_stage}」"
        except Exception as e:
            return f"❌ 阶段更新失败：{str(e)}"
    
    def get_projects_by_stage(self, stage, limit=100):
        """获取阶段项目列表"""
        try:
            with get_db() as db:
                projects = db.query(
                    Project.id, Project.name, Project.marked, Project.remark, 
                    Project.files, Project.update_time
                ).filter(Project.stage == stage).order_by(
                    Project.update_time.desc()
                ).limit(limit).all()
                
                return [{
                    "id": p.id,
                    "name": p.name,
                    "marked": p.marked,
                    "remark": p.remark or "无",
                    "files": p.files or [],
                    "update_time": p.update_time.strftime("%m-%d %H:%M") if p.update_time else "未知"
                } for p in projects]
        except Exception as e:
            print(f"查询出错：{e}")
            return []
    
    def get_project_detail(self, project_id):
        """获取项目详情"""
        try:
            with get_db() as db:
                proj = db.query(Project).filter(Project.id == project_id).first()
                if not proj:
                    return "❌ 项目不存在", []
                
                detail = f"""
╔════════════════════════════════════════╗
║         项目详细信息                   ║
╚════════════════════════════════════════╝

📌 项目ID：{proj.id}
📌 项目名称：{proj.name}
📌 当前阶段：{proj.stage}
📌 标注状态：{'🔆 醒目' if proj.marked == 'highlight' else '⚪ 普通'}

━━━━━━━━━━━━ 基本信息 ━━━━━━━━━━━━
▶ 项目类型：{proj.project_type or '未填写'}
▶ 所属行业：{proj.industry or '未填写'}（代码：{proj.industry_code or '无'}）

━━━━━━━━━━ 核心数据 ━━━━━━━━━━━
💰 财务数据：{proj.financial_data or '未填写'}
👥 项目团队：{proj.team or '未填写'}
📊 商业模式：{proj.business_model or '未填写'}
💎 核心资源：{proj.core_resource or '未填写'}
📈 市场占有率：{proj.market_share or '未填写'}
🎯 商业展望：{proj.business_outlook or '未填写'}

━━━━━━━━━━ 其他信息 ━━━━━━━━━━━
📝 备注：{proj.remark or '无'}
📎 附件数量：{len(proj.files) if proj.files else 0}

⏰ 创建时间：{proj.create_time.strftime('%Y-%m-%d %H:%M') if proj.create_time else '未知'}
🕐 更新时间：{proj.update_time.strftime('%Y-%m-%d %H:%M') if proj.update_time else '未知'}
                """
                files_list = get_file_objects(proj.files) if proj.files else []
                return detail, files_list
        except Exception as e:
            return f"❌ 查询失败：{str(e)}", []

pm = ProjectManager()

# ====================== 6. UI界面 ======================
def create_stage_tab(stage_name):
    """创建阶段标签页"""
    with gr.Tab(stage_name) as tab:
        gr.Markdown(f"### 📁 {stage_name} 管理")
        
        with gr.Accordion("➕ 新增项目", open=False):
            with gr.Row():
                with gr.Column(scale=1):
                    project_name = gr.Textbox(label="项目名称 *", placeholder="必填")
                    project_type = gr.Textbox(label="项目类型", placeholder="如：股权/债权/并购")
                    industry = gr.Textbox(label="所属行业", placeholder="如：文化旅游")
                    industry_code = gr.Textbox(label="行业代码", placeholder="如：R90")
                
                with gr.Column(scale=1):
                    marked_input = gr.Radio(["normal", "highlight"], label="项目标注", value="normal")
                    remark_input = gr.Textbox(label="备注信息", lines=3, placeholder="可填写项目背景、注意事项等...")
            
            with gr.Row():
                financial_data = gr.Textbox(label="核心财务数据", lines=2, placeholder="收入/利润/估值等")
                team = gr.Textbox(label="项目团队", lines=2, placeholder="负责人、成员、分工")
            
            with gr.Row():
                business_model = gr.Textbox(label="商业模式", lines=2, placeholder="盈利模式、业务逻辑")
                core_resource = gr.Textbox(label="核心竞争资源", lines=2, placeholder="牌照/渠道/技术等")
            
            with gr.Row():
                market_share = gr.Textbox(label="市场占有率", placeholder="如：15%")
                business_outlook = gr.Textbox(label="商业展望", lines=2, placeholder="未来预期")
                other_info = gr.Textbox(label="其他", lines=2, placeholder="补充信息")
            
            with gr.Row():
                file_upload = gr.Files(label="上传附件", file_types=[".pdf", ".docx", ".xlsx", ".pptx", ".jpg", ".png", ".txt"])
            
            with gr.Row():
                add_btn = gr.Button("✅ 提交项目", variant="primary", size="lg")
                add_output = gr.Textbox(label="操作结果", interactive=False, visible=True)
        
        with gr.Accordion("📋 项目列表", open=True):
            project_table = gr.Dataframe(
                headers=["项目ID", "项目名称", "标注", "备注", "附件数", "更新"],
                datatype=["str", "str", "str", "str", "number", "str"],
                interactive=False, wrap=True, height=300
            )
            
            with gr.Row():
                with gr.Column(scale=2):
                    selected_id = gr.Textbox(label="🔍 输入项目ID", placeholder="从上方表格复制项目ID", scale=2)
                with gr.Column(scale=1):
                    view_detail_btn = gr.Button("📄 查看详情", variant="secondary")
                    del_btn = gr.Button("🗑️ 删除项目", variant="stop")
            
            with gr.Row():
                new_stage_dropdown = gr.Dropdown(choices=PROJECT_STAGES, label="移至阶段", value=stage_name)
                move_stage_btn = gr.Button("🔄 迁移项目", variant="secondary")
            
            with gr.Row():
                detail_output = gr.Textbox(label="项目详情", lines=15, max_lines=20)
            
            with gr.Row():
                files_output = gr.Files(label="附件列表", interactive=False)
        
        def refresh_table():
            projects = pm.get_projects_by_stage(stage_name)
            if not projects:
                return [[]]
            table_data = []
            for p in projects:
                marked_text = "🔆 醒目" if p["marked"] == "highlight" else "⚪ 普通"
                remark_short = p["remark"][:15] + "..." if len(p["remark"]) > 15 else p["remark"]
                table_data.append([p["id"], p["name"], marked_text, remark_short, len(p["files"]), p["update_time"]])
            return table_data
        
        def handle_view_detail(project_id):
            if not project_id:
                return "❌ 请输入项目ID", []
            return pm.get_project_detail(project_id)
        
        def clear_form():
            return ["", "", "", "", "normal", "", "", "", "", "", "", "", "", None]
        
        tab.select(
            fn=refresh_table, 
            outputs=project_table
        )
        
        add_btn.click(
            fn=lambda n, t, i, ic, m, r, fd, tm, bm, cr, ms, bo, oi, files: 
                pm.add_project(stage_name, {
                    "项目名称": n, 
                    "项目类型": t, 
                    "所属行业": i, 
                    "所属行业代码": ic,
                    "项目阶段": stage_name, 
                    "项目核心财务数据": fd, 
                    "项目团队": tm,
                    "商业模式": bm, 
                    "核心竞争资源": cr, 
                    "市场占有率": ms,
                    "商业展望": bo, 
                    "其他": oi
                }, r, m, files),
            inputs=[
                project_name, project_type, industry, industry_code, 
                marked_input, remark_input,
                financial_data, team, business_model, core_resource, 
                market_share, business_outlook, other_info, file_upload
            ],
            outputs=add_output
        ).then(
            fn=refresh_table, 
            outputs=project_table
        ).then(
            fn=clear_form, 
            outputs=[
                project_name, project_type, industry, industry_code, 
                marked_input, remark_input,
                financial_data, team, business_model, core_resource, 
                market_share, business_outlook, other_info, file_upload
            ]
        )
        
        view_detail_btn.click(
            fn=handle_view_detail, 
            inputs=selected_id, 
            outputs=[detail_output, files_output]
        )
        
        del_btn.click(
            fn=pm.delete_project, 
            inputs=selected_id, 
            outputs=add_output
        ).then(
            fn=refresh_table, 
            outputs=project_table
        ).then(
            fn=lambda: ("", "", []), 
            outputs=[selected_id, detail_output, files_output]
        )
        
        move_stage_btn.click(
            fn=pm.update_project_stage, 
            inputs=[selected_id, new_stage_dropdown], 
            outputs=add_output
        ).then(
            fn=refresh_table, 
            outputs=project_table
        ).then(
            fn=lambda: ("", "", []), 
            outputs=[selected_id, detail_output, files_output]
        )

# ====================== 7. 主界面 ======================
with gr.Blocks(title=TOOL_NAME, theme=gr.themes.Soft()) as demo:
    gr.Markdown(f"# 🏦 {TOOL_NAME}")
    gr.Markdown("### 投资业务全流程管理系统 | 简单 · 高效 · 安全")
    
    for stage_name in PROJECT_STAGES:
        create_stage_tab(stage_name)
    
    gr.Markdown("---")
    gr.Markdown(f"© {datetime.now().year} 旅投银创投资业务团队 | 版本 2.3")
    gr.Markdown(f"📁 数据存储路径：`{BASE_DIR}`")

if __name__ == "__main__":
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║     {TOOL_NAME} 启动成功                                    ║
    ╠══════════════════════════════════════════════════════════╣
    ║  📂 数据目录: {BASE_DIR}                 
    ║  💾 数据库: {DB_PATH.name}                                   
    ║  🌐 访问地址: http://localhost:7860                       
    ║  ⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}               
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Gradio 3.50.2 兼容版本 - 删除了不支持的参数
    demo.launch()