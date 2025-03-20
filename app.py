from flask import Flask, request, render_template, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_babel import Babel, gettext as _
from flask_migrate import Migrate
from sqlalchemy import or_

"""
-------------------------------------------------------
 Flask 应用示例（优化版）
 1. 使用 Flask-Babel 多语言支持
 2. 使用 Flask-Login 用户登录/登出
 3. Excel 文件上传、数据清洗（去除重复列）并导入数据库
 4. 数据导出至 Excel
 5. 搜索、空值搜索及整体空值统计功能
    - 搜索时支持仅显示空值订单（空字符串和 "0" 均视为缺失）
 6. Dashboard 表头增加两行：
    - 第一行显示各列负责部门（若该列在当前查询中存在缺失则标红，否则黑色）
    - 第二行显示实际列名，并在 title 中提示整个数据库中该字段的缺失数量
 7. 新增订单和编辑订单功能，支持备注（remark）字段
-------------------------------------------------------
"""

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# ========= 数据库配置 =========
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ========= 文件上传目录 =========
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ========= 初始化 Flask-Login =========
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========= Flask-Babel =========
app.config['BABEL_DEFAULT_LOCALE'] = 'zh'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'zh']
def get_locale():
    return session.get('lang', 'zh')
babel = Babel(app, locale_selector=get_locale)

# ========= 模拟用户数据 =========
users = {
    'admin': {'password': 'admin123', 'role': 'admin'},
    'user': {'password': 'user123', 'role': 'user'}
}
class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role
@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id, users[user_id]['role'])
    return None

# ========= 切换语言 =========
@app.route('/switch_language/<lang>')
def switch_language(lang):
    if lang in ['en', 'zh']:
        session.permanent = True
        session['lang'] = lang
    return redirect(request.referrer or url_for('dashboard'))

# ========= 数据库模型 =========
class Order(db.Model):
    """
    订单模型。
    注意：Excel 导入时使用的键必须与 Excel 中的列名完全一致（包括换行符）。
    示例列名：
      "#\n输入序号", "SUPPLIER/SHIPPER\n发货人", "PO#\n订单号", "Material Code\nSAP料号",
      "BOM\n物料名称", "Material Size\n型号/规格/尺寸", "Quantity\n数量", "UNIT\n单位",
      "MBL# / MAWB#\n船东提单号", "柜子数", "CNTR#\n柜号", "HBL#\n提单号", "POL\n起运港",
      "ETD\n开船日", "POD\n目的港", "POD ETA\n实际到港日期", "EST. DELIVERY DATE\n预估到厂日"
    备注字段 remark 用于说明缺失原因等信息。
    """
    id = db.Column(db.Integer, primary_key=True)
    input_number = db.Column(db.String(100))
    supplier_shipper = db.Column(db.String(200))
    po_number = db.Column(db.String(100))
    material_code = db.Column(db.String(100))
    bom_material_name = db.Column(db.String(200))
    material_size = db.Column(db.String(200))
    quantity = db.Column(db.String(100))
    unit = db.Column(db.String(50))
    mbl_number = db.Column(db.String(100))
    container_count = db.Column(db.String(50))
    container_number = db.Column(db.String(100))
    hbl_number = db.Column(db.String(100))
    pol = db.Column(db.String(100))
    etd = db.Column(db.String(100))
    pod = db.Column(db.String(100))
    pod_eta = db.Column(db.String(100))
    estimated_delivery_date = db.Column(db.String(100))
    remark = db.Column(db.String(500), default='')  # 备注字段
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========= Excel 导入及数据清洗 =========
def import_excel_to_db():
    """
    从 UPLOAD_FOLDER 下的 material.xlsx 文件中读取数据，
    对列名去空格、去重复并填充空值后，逐行转换为 Order 对象插入数据库。
    注意：Excel 中的列名必须和以下 row.get() 使用的键一致（包括换行符）。
    """
    excel_file = os.path.join(app.config['UPLOAD_FOLDER'], 'material.xlsx')
    if os.path.exists(excel_file):
        try:
            data = pd.read_excel(excel_file, dtype=str)
            data.columns = data.columns.str.strip()
            print("【调试】原始列名:", data.columns.tolist())
            data = data.loc[:, ~data.columns.duplicated()]
            print("【调试】去重后列名:", data.columns.tolist())
            data = data.fillna('')
            if not data.empty:
                print("【调试】第一行数据:", data.iloc[0].to_dict())
            else:
                print("【警告】Excel 文件中无数据！")
            for index, row in data.iterrows():
                print(f"【调试】Row {index} 数据:", row.to_dict())
                order = Order(
                    input_number=str(row.get('#\n输入序号', '')).strip(),
                    supplier_shipper=str(row.get('SUPPLIER/SHIPPER\n发货人', '')).strip(),
                    po_number=str(row.get('PO#\n订单号', '')).strip(),
                    material_code=str(row.get('Material Code\nSAP料号', '')).strip(),
                    bom_material_name=str(row.get('BOM\n物料名称', '')).strip(),
                    material_size=str(row.get('Material Size\n型号/规格/尺寸', '')).strip(),
                    quantity=str(row.get('Quantity\n数量', '')).strip(),
                    unit=str(row.get('UNIT\n单位', '')).strip(),
                    mbl_number=str(row.get('MBL# / MAWB#\n船东提单号', '')).strip(),
                    container_count=str(row.get('柜子数', '')).strip(),
                    container_number=str(row.get('CNTR#\n柜号', '')).strip(),
                    hbl_number=str(row.get('HBL#\n提单号', '')).strip(),
                    pol=str(row.get('POL\n起运港', '')).strip(),
                    etd=str(row.get('ETD\n开船日', '')).strip(),
                    pod=str(row.get('POD\n目的港', '')).strip(),
                    pod_eta=str(row.get('POD ETA\n实际到港日期', '')).strip(),
                    estimated_delivery_date=str(row.get('EST. DELIVERY DATE\n预估到厂日', '')).strip(),
                )
                db.session.add(order)
            db.session.commit()
            flash('Data imported successfully!')
        except Exception as e:
            flash(f'Failed to import data: {str(e)}')
            print("【错误】导入异常:", e)

# ========= 路由 =========

# 根路由，重定向到登录页面
@app.route('/')
def home():
    return redirect(url_for('login'))

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            user = User(username, users[username]['role'])
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Dashboard 路由，支持搜索和空值过滤
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # 搜索部分
    if request.method == 'POST':
        only_missing = request.form.get('only_missing')
        if only_missing:
            # 过滤条件：任一必填字段为空或为 "0"
            fields = ["input_number", "supplier_shipper", "po_number",
                      "material_code", "bom_material_name", "material_size",
                      "quantity", "unit", "mbl_number", "container_count",
                      "container_number", "hbl_number", "pol", "etd",
                      "pod", "pod_eta", "estimated_delivery_date"]
            missing_filters = [(getattr(Order, field) == '') | (getattr(Order, field) == '0') for field in fields]
            orders = Order.query.filter(or_(*missing_filters)).order_by(Order.created_at.desc()).all()
        else:
            filters = []
            search_fields = ["input_number", "supplier_shipper", "po_number",
                             "material_code", "bom_material_name", "material_size",
                             "quantity", "unit", "mbl_number", "container_count",
                             "container_number", "hbl_number", "pol", "etd",
                             "pod", "pod_eta", "estimated_delivery_date"]
            for field in search_fields:
                value = request.form.get(f'search_{field}', '').strip()
                if value:
                    filters.append(getattr(Order, field).contains(value))
            if filters:
                orders = Order.query.filter(*filters).order_by(Order.created_at.desc()).all()
            else:
                orders = Order.query.order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.order_by(Order.created_at.desc()).all()

    # 计算当前查询中各字段是否存在空值（空字符串或 "0" 视为缺失），用于表头显示
    columns_to_check = ["input_number", "supplier_shipper", "po_number",
                        "material_code", "bom_material_name", "material_size",
                        "quantity", "unit", "mbl_number", "container_count",
                        "container_number", "hbl_number", "pol", "etd",
                        "pod", "pod_eta", "estimated_delivery_date"]
    missing_map = {}
    for col in columns_to_check:
        missing_map[col] = any((not getattr(order, col)) or (getattr(order, col) == '0') for order in orders)

    # 统计整个数据库中每个字段的缺失数量（空字符串或 "0" 视为缺失）
    all_orders = Order.query.all()
    total_missing = {}
    for col in columns_to_check:
        total_missing[col] = sum(1 for order in all_orders if (not getattr(order, col)) or (getattr(order, col) == '0'))

    return render_template('dashboard.html', orders=orders, missing_map=missing_map, total_missing=total_missing)

# 新增订单路由
@app.route('/add_order', methods=['GET', 'POST'])
@login_required
def add_order():
    if request.method == 'POST':
        new_order = Order(
            input_number=request.form.get('input_number', ''),
            supplier_shipper=request.form.get('supplier_shipper', ''),
            po_number=request.form.get('po_number', ''),
            material_code=request.form.get('material_code', ''),
            bom_material_name=request.form.get('bom_material_name', ''),
            material_size=request.form.get('material_size', ''),
            quantity=request.form.get('quantity', ''),
            unit=request.form.get('unit', ''),
            mbl_number=request.form.get('mbl_number', ''),
            container_count=request.form.get('container_count', ''),
            container_number=request.form.get('container_number', ''),
            hbl_number=request.form.get('hbl_number', ''),
            pol=request.form.get('pol', ''),
            etd=request.form.get('etd', ''),
            pod=request.form.get('pod', ''),
            pod_eta=request.form.get('pod_eta', ''),
            estimated_delivery_date=request.form.get('estimated_delivery_date', ''),
            remark=request.form.get('remark', '')
        )
        db.session.add(new_order)
        db.session.commit()
        flash('New order added successfully!')
        return redirect(url_for('dashboard'))
    return render_template('add_order.html')

# 编辑订单路由
@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == 'POST':
        order.input_number = request.form.get('input_number', '')
        order.supplier_shipper = request.form.get('supplier_shipper', '')
        order.po_number = request.form.get('po_number', '')
        order.material_code = request.form.get('material_code', '')
        order.bom_material_name = request.form.get('bom_material_name', '')
        order.material_size = request.form.get('material_size', '')
        order.quantity = request.form.get('quantity', '')
        order.unit = request.form.get('unit', '')
        order.mbl_number = request.form.get('mbl_number', '')
        order.container_count = request.form.get('container_count', '')
        order.container_number = request.form.get('container_number', '')
        order.hbl_number = request.form.get('hbl_number', '')
        order.pol = request.form.get('pol', '')
        order.etd = request.form.get('etd', '')
        order.pod = request.form.get('pod', '')
        order.pod_eta = request.form.get('pod_eta', '')
        order.estimated_delivery_date = request.form.get('estimated_delivery_date', '')
        order.remark = request.form.get('remark', '')
        db.session.commit()
        flash('Order updated successfully!')
        return redirect(url_for('dashboard'))
    return render_template('edit_order.html', order=order)

# 导出 Excel 路由
@app.route('/export', methods=['GET'])
@login_required
def export_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    data = {
        "#\n输入序号": [o.input_number for o in orders],
        "SUPPLIER/SHIPPER\n发货人": [o.supplier_shipper for o in orders],
        "PO#\n订单号": [o.po_number for o in orders],
        "Material Code\nSAP料号": [o.material_code for o in orders],
        "BOM\n物料名称": [o.bom_material_name for o in orders],
        "Material Size\n型号/规格/尺寸": [o.material_size for o in orders],
        "Quantity\n数量": [o.quantity for o in orders],
        "UNIT\n单位": [o.unit for o in orders],
        "MBL# / MAWB#\n船东提单号": [o.mbl_number for o in orders],
        "柜子数": [o.container_count for o in orders],
        "CNTR#\n柜号": [o.container_number for o in orders],
        "HBL#\n提单号": [o.hbl_number for o in orders],
        "POL\n起运港": [o.pol for o in orders],
        "ETD\n开船日": [o.etd for o in orders],
        "POD\n目的港": [o.pod for o in orders],
        "POD ETA\n实际到港日期": [o.pod_eta for o in orders],
        "EST. DELIVERY DATE\n预估到厂日": [o.estimated_delivery_date for o in orders],
        "Remark": [o.remark for o in orders],
    }
    df = pd.DataFrame(data)
    output_file = os.path.join(app.config['UPLOAD_FOLDER'], 'exported_orders.xlsx')
    df.to_excel(output_file, index=False)
    return send_file(output_file, as_attachment=True)

# 上传 Excel 路由
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if current_user.role != 'admin':
        flash('You do not have permission to upload files.', 'error')
        return redirect(url_for('dashboard'))
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('dashboard'))
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('dashboard'))
    if not file.filename.endswith('.xlsx'):
        flash('Invalid file type. Please upload an Excel file.', 'error')
        return redirect(url_for('dashboard'))
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'material.xlsx')
    file.save(file_path)
    try:
        import_excel_to_db()
        flash('File uploaded and data imported successfully!', 'success')
    except Exception as e:
        flash(f'Error importing file: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        # 开发阶段：删除旧表并重建（会清空所有数据，请谨慎使用）
        db.drop_all()
        db.create_all()
    app.run(debug=True, port=5000)
