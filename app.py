from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import mysql.connector
from werkzeug.utils import secure_filename
from functools import wraps
import logging
import secrets
from sqlalchemy import text
from sqlalchemy.sql import func

# .env dosyasını yükle
load_dotenv()

# Flask uygulamasını oluştur
app = Flask(__name__)
app.debug = False  # Debug modunu kapat

# Loglama ayarları
logging.basicConfig(
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.log'),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'gizli-anahtar-buraya')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# İzin verilen dosya uzantıları
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# MySQL bağlantı bilgileri
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'car_rental')

def validate_dates(baslangic, bitis):
    """Kiralama tarihlerini doğrular"""
    if baslangic >= bitis:
        raise ValueError("Başlangıç tarihi bitiş tarihinden önce olmalıdır.")
    if baslangic < datetime.now():
        raise ValueError("Başlangıç tarihi geçmiş bir tarih olamaz.")
    if bitis < datetime.now():
        raise ValueError("Bitiş tarihi geçmiş bir tarih olamaz.")
    if (bitis - baslangic).days > 30:
        raise ValueError("Kiralama süresi 30 günden fazla olamaz.")

# SQLAlchemy bağlantı URL'si
SQLALCHEMY_DATABASE_URI = f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLAlchemy ve Login Manager'ı başlat
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Veritabanı Modelleri
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120))
    is_admin = db.Column(db.Boolean, default=False)
    kiralamalar = db.relationship('Kiralama', backref='kullanici', lazy=True)
    reset_token = db.Column(db.String(255))
    reset_token_expires = db.Column(db.DateTime)

    def set_password(self, password):
        if not password:
            raise ValueError("Şifre boş olamaz")
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Araba(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marka = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    yil = db.Column(db.Integer, nullable=False)
    gunluk_fiyat = db.Column(db.Float, nullable=False)
    resim_url = db.Column(db.String(200))
    aciklama = db.Column(db.Text)
    kategori = db.Column(db.String(50), nullable=False, default='Diğer')
    kiralamalar = db.relationship('Kiralama', backref='araba', lazy=True)

class Kiralama(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    baslangic_tarihi = db.Column(db.DateTime, nullable=False)
    bitis_tarihi = db.Column(db.DateTime, nullable=False)
    toplam_fiyat = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    araba_id = db.Column(db.Integer, db.ForeignKey('araba.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def check_database():
    """Veritabanındaki araçları kontrol et ve raporla"""
    with app.app_context():
        try:
            arabalar = Araba.query.all()
            logging.info(f"Veritabanında {len(arabalar)} araç bulundu.")
            for araba in arabalar:
                logging.info(f"{araba.marka} {araba.model}: {araba.resim_url}")
            return arabalar
        except Exception as e:
            logging.error(f"Veritabanı kontrolü sırasında hata oluştu: {e}")
            raise e

def reset_database():
    """Veritabanını sıfırlar ve yeniden oluşturur"""
    try:
        # MySQL bağlantısı oluştur
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = connection.cursor()

        # Veritabanını sil ve yeniden oluştur
        cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
        cursor.execute(f"CREATE DATABASE {DB_NAME}")
        logging.info(f"Veritabanı '{DB_NAME}' başarıyla sıfırlandı.")

        cursor.close()
        connection.close()

        # SQLAlchemy ile tabloları oluştur
        with app.app_context():
            db.create_all()
            logging.info("Tüm tablolar başarıyla oluşturuldu.")
            
            # Admin kullanıcısını oluştur
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            logging.info("Admin kullanıcısı oluşturuldu.")
            
            # Örnek araçları ekle
            seed_database()
            logging.info("Örnek araçlar eklendi.")

    except Exception as e:
        logging.error(f"Veritabanı sıfırlanırken hata oluştu: {e}")
        raise e

def handle_image_upload(resim, default_filename='default.jpg'):
    if resim and allowed_file(resim.filename):
        try:
            # Dosya adını güvenli hale getir
            filename = secure_filename(resim.filename)
            
            # Dosya uzantısını kontrol et ve düzelt
            if '.' not in filename:
                filename = f"{filename}.jpg"
            elif filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
                filename = f"{filename.rsplit('.', 1)[0]}.jpg"
            
            # Benzersiz dosya adı oluştur
            unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
            
            # Resim dosyasının tam yolunu oluştur
            resim_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Upload klasörünün varlığını kontrol et
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Klasör izinlerini ayarla
            os.chmod(app.config['UPLOAD_FOLDER'], 0o755)
            
            # Resmi kaydet
            resim.save(resim_path)
            logging.info(f"Resim başarıyla kaydedildi: {resim_path}")
            
            # Dosya izinlerini ayarla
            os.chmod(resim_path, 0o644)
            
            # Dosya sahibini www-data olarak ayarla
            os.system(f"sudo chown www-data:www-data {resim_path}")
            os.system(f"sudo chown www-data:www-data {app.config['UPLOAD_FOLDER']}")
            
            # Dosyanın varlığını ve izinlerini kontrol et
            if os.path.exists(resim_path):
                # Dosya izinlerini kontrol et
                stat = os.stat(resim_path)
                logging.info(f"Resim dosyası başarıyla oluşturuldu: {resim_path}")
                logging.info(f"Dosya izinleri: {oct(stat.st_mode)}")
                logging.info(f"Dosya sahibi: {stat.st_uid}:{stat.st_gid}")
                logging.info(f"Dosya adı: {unique_filename}")
                return unique_filename
            else:
                logging.error(f"Resim dosyası oluşturulamadı: {resim_path}")
                return default_filename
                
        except Exception as e:
            logging.error(f"Resim yüklenirken hata oluştu: {e}")
            return default_filename
    else:
        logging.warning(f"Geçersiz resim formatı veya resim yüklenmedi: {resim.filename if resim else 'No file'}")
        return default_filename

def delete_image(filename):
    if filename and filename != 'default.jpg':
        try:
            resim_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(resim_path):
                os.remove(resim_path)
                logging.info(f"Resim silindi: {resim_path}")
        except Exception as e:
            logging.error(f"Resim silinirken hata oluştu: {e}")

# Upload klasörünü oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Route'lar
@app.route('/')
def index():
    try:
        arabalar = Araba.query.all()
        logging.info(f"Ana sayfa yüklendi. {len(arabalar)} araç bulundu.")
        return render_template('index.html', arabalar=arabalar)
    except Exception as e:
        logging.error(f"Ana sayfa yüklenirken hata oluştu: {e}")
        return render_template('error.html', error=str(e)), 500

@app.route('/admin/panel')
@admin_required
def admin_panel():
    try:
        arabalar = Araba.query.all()
        kiralamalar = Kiralama.query.all()
        kullanicilar = User.query.all()
        return render_template('admin_panel.html', 
                             arabalar=arabalar, 
                             kiralamalar=kiralamalar, 
                             kullanicilar=kullanicilar)
    except Exception as e:
        logging.error(f"Admin paneli yüklenirken hata oluştu: {e}")
        return render_template('error.html', error=str(e)), 500

@app.route('/admin/araba/ekle', methods=['GET', 'POST'])
@admin_required
def araba_ekle():
    if request.method == 'POST':
        try:
            # Form verilerini al
            marka = request.form.get('marka')
            model = request.form.get('model')
            yil = request.form.get('yil')
            gunluk_fiyat = request.form.get('gunluk_fiyat')
            aciklama = request.form.get('aciklama', '')

            # Zorunlu alanları kontrol et
            if not all([marka, model, yil, gunluk_fiyat]):
                flash('Lütfen tüm zorunlu alanları doldurun!', 'error')
                return redirect(url_for('araba_ekle'))
                
            # Resim yükleme
            resim_url = 'default.jpg'
            if 'resim' in request.files:
                resim = request.files['resim']
                if resim.filename:
                    resim_url = handle_image_upload(resim)
                    logging.info(f"Yüklenen resim dosyası: {resim_url}")

            # Yeni araç oluştur
            yeni_araba = Araba(
                marka=marka,
                model=model,
                yil=int(yil),
                gunluk_fiyat=float(gunluk_fiyat),
                resim_url=resim_url,
                aciklama=aciklama
            )

            # Veritabanına kaydet
            db.session.add(yeni_araba)
            db.session.commit()
            
            logging.info(f"Yeni araç eklendi: {yeni_araba.marka} {yeni_araba.model}")
            flash('Araç başarıyla eklendi!', 'success')
            return redirect(url_for('admin_panel'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Araç eklenirken hata oluştu: {e}")
            flash('Araç eklenirken bir hata oluştu!', 'error')
            return redirect(url_for('araba_ekle'))

    return render_template('araba_ekle.html')

@app.route('/admin/araba/sil/<int:id>')
@admin_required
def araba_sil(id):
    try:
        araba = db.session.get(Araba, id)
        if not araba:
            flash('Araç bulunamadı!', 'error')
            return redirect(url_for('admin_panel'))
            
        # Aracın kiralama kayıtlarını kontrol et
        aktif_kiralamalar = Kiralama.query.filter_by(araba_id=id).first()
        
        if aktif_kiralamalar:
            flash('Bu aracın aktif kiralama kayıtları var. Önce kiralama kayıtlarını silmelisiniz!', 'error')
            return redirect(url_for('admin_panel'))
        
        # Resmi sil
        delete_image(araba.resim_url)
        
        # Aracı sil
        db.session.delete(araba)
        db.session.commit()
        
        flash('Araç başarıyla silindi!', 'success')
        return redirect(url_for('admin_panel'))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Araç silinirken hata oluştu: {e}")
        flash('Araç silinirken bir hata oluştu!', 'error')
        return redirect(url_for('admin_panel'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Kullanıcı adı ve e-posta kontrolü
            if User.query.filter_by(username=username).first():
                flash('Bu kullanıcı adı zaten kullanılıyor.', 'error')
                logging.warning(f"Kayıt denemesi başarısız: Kullanıcı adı zaten mevcut - {username}")
                return redirect(url_for('register'))
                
            if User.query.filter_by(email=email).first():
                flash('Bu e-posta adresi zaten kullanılıyor.', 'error')
                logging.warning(f"Kayıt denemesi başarısız: E-posta zaten mevcut - {email}")
                return redirect(url_for('register'))
            
            # Yeni kullanıcı oluştur
            user = User(
                username=username,
                email=email,
                is_admin=False
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash('Kayıt başarılı! Şimdi giriş yapabilirsiniz.', 'success')
            logging.info(f"Yeni kullanıcı kaydı başarılı: {username}")
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash('Kayıt sırasında bir hata oluştu. Lütfen tekrar deneyin.', 'error')
            logging.error(f"Kayıt hatası: {e}")
            return redirect(url_for('register'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            user = User.query.filter_by(username=username).first()
            
            if not user:
                flash('Bu kullanıcı adı ile kayıtlı kullanıcı bulunamadı.', 'error')
                logging.warning(f"Giriş denemesi başarısız: Kullanıcı bulunamadı - {username}")
                return redirect(url_for('login'))
            
            if not user.password_hash:
                flash('Kullanıcı şifresi bulunamadı. Lütfen yönetici ile iletişime geçin.', 'error')
                logging.error(f"Kullanıcı şifresi bulunamadı: {username}")
                return redirect(url_for('login'))
            
            if not user.check_password(password):
                flash('Girdiğiniz şifre yanlış.', 'error')
                logging.warning(f"Giriş denemesi başarısız: Yanlış şifre - {username}")
                return redirect(url_for('login'))
            
            login_user(user)
            flash('Başarıyla giriş yaptınız!', 'success')
            logging.info(f"Kullanıcı başarıyla giriş yaptı: {username}")
            return redirect(url_for('index'))
            
        except Exception as e:
            flash('Giriş yapılırken bir hata oluştu. Lütfen tekrar deneyin.', 'error')
            logging.error(f"Giriş işlemi sırasında hata oluştu: {e}")
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/araba/<int:id>')
def araba_detay(id):
    araba = db.session.get(Araba, id)
    if not araba:
        flash('Araç bulunamadı!', 'error')
        return redirect(url_for('index'))
    return render_template('araba_detay.html', araba=araba)

@app.route('/kirala/<int:araba_id>', methods=['GET', 'POST'])
@login_required
def kirala(araba_id):
    araba = Araba.query.get_or_404(araba_id)
    
    if request.method == 'POST':
        try:
            baslangic = datetime.strptime(request.form.get('baslangic'), '%Y-%m-%d')
            bitis = datetime.strptime(request.form.get('bitis'), '%Y-%m-%d')
            
            validate_dates(baslangic, bitis)
            
            # Aynı tarihlerde başka kiralama var mı kontrol et
            mevcut_kiralamalar = Kiralama.query.filter(
                Kiralama.araba_id == araba_id,
                Kiralama.baslangic_tarihi <= bitis,
                Kiralama.bitis_tarihi >= baslangic
            ).first()
            
            if mevcut_kiralamalar:
                flash('Seçilen tarihlerde araç zaten kiralanmış!')
                return redirect(url_for('kirala', araba_id=araba_id))
            
            gun_farki = (bitis - baslangic).days
            toplam_fiyat = araba.gunluk_fiyat * gun_farki
            
            kiralama = Kiralama(
                baslangic_tarihi=baslangic,
                bitis_tarihi=bitis,
                toplam_fiyat=toplam_fiyat,
                user_id=current_user.id,
                araba_id=araba.id
            )
            
            db.session.add(kiralama)
            db.session.commit()
            
            flash('Araç başarıyla kiralandı!')
            return redirect(url_for('index'))
            
        except ValueError as e:
            flash(str(e))
            return redirect(url_for('kirala', araba_id=araba_id))
        except Exception as e:
            db.session.rollback()
            logging.error(f"Kiralama işlemi sırasında hata oluştu: {e}")
            flash('Kiralama işlemi sırasında bir hata oluştu!')
            return redirect(url_for('kirala', araba_id=araba_id))
    
    return render_template('kirala.html', araba=araba)

@app.route('/kiralarim')
@login_required
def kiralarim():
    try:
        kiralamalar = Kiralama.query.filter_by(user_id=current_user.id).order_by(Kiralama.baslangic_tarihi.desc()).all()
        return render_template('kiralarim.html', kiralamalar=kiralamalar, datetime=datetime)
    except Exception as e:
        logging.error(f"Kiralama listesi yüklenirken hata oluştu: {e}")
        return render_template('error.html', error=str(e)), 500

@app.route('/kiralama/iptal/<int:id>')
@login_required
def kiralama_iptal(id):
    try:
        kiralama = db.session.get(Kiralama, id)
        if not kiralama:
            flash('Kiralama bulunamadı!', 'error')
            return redirect(url_for('kiralarim'))
        
        # Kullanıcının kendi kiralaması mı kontrol et
        if kiralama.user_id != current_user.id:
            flash('Bu kiralama işlemini iptal etme yetkiniz yok!', 'error')
            return redirect(url_for('kiralarim'))
        
        # Kiralama başlamış mı kontrol et
        if kiralama.baslangic_tarihi <= datetime.now():
            flash('Başlamış kiralama işlemi iptal edilemez!', 'error')
            return redirect(url_for('kiralarim'))
        
        db.session.delete(kiralama)
        db.session.commit()
        
        flash('Kiralama işlemi başarıyla iptal edildi!', 'success')
        return redirect(url_for('kiralarim'))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Kiralama iptal edilirken hata oluştu: {e}")
        flash('Kiralama iptal edilirken bir hata oluştu!', 'error')
        return redirect(url_for('kiralarim'))

@app.route('/arama')
def araba_ara():
    try:
        query = request.args.get('q', '')
        min_fiyat = request.args.get('min_fiyat', type=float)
        max_fiyat = request.args.get('max_fiyat', type=float)
        min_yil = request.args.get('min_yil', type=int)
        max_yil = request.args.get('max_yil', type=int)
        
        arabalar = Araba.query
        
        if query:
            arabalar = arabalar.filter(
                db.or_(
                    Araba.marka.ilike(f'%{query}%'),
                    Araba.model.ilike(f'%{query}%')
                )
            )
        
        if min_fiyat is not None:
            arabalar = arabalar.filter(Araba.gunluk_fiyat >= min_fiyat)
        
        if max_fiyat is not None:
            arabalar = arabalar.filter(Araba.gunluk_fiyat <= max_fiyat)
        
        if min_yil is not None:
            arabalar = arabalar.filter(Araba.yil >= min_yil)
        
        if max_yil is not None:
            arabalar = arabalar.filter(Araba.yil <= max_yil)
        
        arabalar = arabalar.all()
        return render_template('arama.html', arabalar=arabalar, query=query)
    except Exception as e:
        logging.error(f"Arama yapılırken hata oluştu: {e}")
        return render_template('error.html', error=str(e)), 500

@app.route('/istatistik')
@login_required
def istatistik():
    try:
        # Toplam kiralama sayısı
        toplam_kiralama = Kiralama.query.count()
        
        # Toplam gelir
        toplam_gelir = db.session.query(func.sum(Kiralama.toplam_fiyat)).scalar() or 0
        
        # En çok kiralanan araçlar
        en_cok_kiralanan = db.session.query(
            Araba.model,
            func.count(Kiralama.id).label('kiralama_sayisi')
        ).join(Kiralama).group_by(Araba.model).order_by(func.count(Kiralama.id).desc()).limit(5).all()
        
        # Aylık kiralama istatistikleri
        aylik_kiralama = db.session.query(
            func.date_format(Kiralama.baslangic_tarihi, '%Y-%m').label('ay'),
            func.count(Kiralama.id).label('kiralama_sayisi')
        ).group_by('ay').order_by('ay').all()
        
        # Araç kategorilerine göre dağılım
        kategori_dagilimi = db.session.query(
            Araba.kategori,
            func.count(Araba.id).label('arac_sayisi')
        ).group_by(Araba.kategori).all()
        
        return render_template('istatistik.html',
                             toplam_kiralama=toplam_kiralama,
                             toplam_gelir=toplam_gelir,
                             en_cok_kiralanan=en_cok_kiralanan,
                             aylik_kiralama=aylik_kiralama,
                             kategori_dagilimi=kategori_dagilimi)
    except Exception as e:
        logging.error(f"İstatistik sayfası yüklenirken hata oluştu: {e}")
        return render_template('error.html', error=str(e)), 500

@app.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    if request.method == 'POST':
        try:
            # E-posta güncelleme
            yeni_email = request.form.get('email')
            if yeni_email and yeni_email != current_user.email:
                if User.query.filter_by(email=yeni_email).first():
                    flash('Bu e-posta adresi zaten kullanılıyor!', 'error')
                    return redirect(url_for('profil'))
                current_user.email = yeni_email
            
            # Şifre güncelleme
            yeni_sifre = request.form.get('yeni_sifre')
            if yeni_sifre:
                mevcut_sifre = request.form.get('mevcut_sifre')
                if not current_user.check_password(mevcut_sifre):
                    flash('Mevcut şifre yanlış!', 'error')
                    return redirect(url_for('profil'))
                current_user.set_password(yeni_sifre)
            
            db.session.commit()
            flash('Profil başarıyla güncellendi!', 'success')
            return redirect(url_for('profil'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Profil güncellenirken hata oluştu: {e}")
            flash('Profil güncellenirken bir hata oluştu!', 'error')
            return redirect(url_for('profil'))
    
    return render_template('profil.html')

@app.route('/sifremi-unuttum', methods=['GET', 'POST'])
def sifremi_unuttum():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            user = User.query.filter_by(email=email).first()
            
            if user:
                # Benzersiz token oluştur
                token = secrets.token_urlsafe(32)
                user.reset_token = token
                user.reset_token_expires = datetime.now() + timedelta(hours=1)
                db.session.commit()
                
                # E-posta gönderme işlemi burada yapılacak
                # Örnek: send_reset_email(user.email, token)
                
                flash('Şifre sıfırlama bağlantısı e-posta adresinize gönderildi.', 'success')
            else:
                flash('Bu e-posta adresi ile kayıtlı kullanıcı bulunamadı.', 'error')
            
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Şifre sıfırlama işlemi sırasında hata oluştu: {e}")
            flash('Şifre sıfırlama işlemi sırasında bir hata oluştu!', 'error')
            return redirect(url_for('sifremi_unuttum'))
    
    return render_template('sifremi_unuttum.html')

@app.route('/sifre-sifirla/<token>', methods=['GET', 'POST'])
def sifre_sifirla(token):
    try:
        user = User.query.filter_by(reset_token=token).first()
        
        if not user or not user.reset_token_expires or user.reset_token_expires < datetime.now():
            flash('Geçersiz veya süresi dolmuş şifre sıfırlama bağlantısı!', 'error')
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            yeni_sifre = request.form.get('yeni_sifre')
            if yeni_sifre:
                user.set_password(yeni_sifre)
                user.reset_token = None
                user.reset_token_expires = None
                db.session.commit()
                
                flash('Şifreniz başarıyla güncellendi! Şimdi giriş yapabilirsiniz.', 'success')
                return redirect(url_for('login'))
        
        return render_template('sifre_sifirla.html')
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Şifre sıfırlama işlemi sırasında hata oluştu: {e}")
        flash('Şifre sıfırlama işlemi sırasında bir hata oluştu!', 'error')
        return redirect(url_for('login'))

# Veritabanı güncelleme fonksiyonu
def update_database():
    try:
        with app.app_context():
            # Önce sütunların var olup olmadığını kontrol et
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'user' 
                AND COLUMN_NAME IN ('reset_token', 'reset_token_expires')
            """))
            existing_columns = [row[0] for row in result]
            
            # Eksik sütunları ekle
            if 'reset_token' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE user 
                    ADD COLUMN reset_token VARCHAR(100)
                """))
            
            if 'reset_token_expires' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE user 
                    ADD COLUMN reset_token_expires DATETIME
                """))
            
            # Araba tablosunda kategori sütununu kontrol et
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'araba' 
                AND COLUMN_NAME = 'kategori'
            """))
            if not result.fetchone():
                db.session.execute(text("""
                    ALTER TABLE araba 
                    ADD COLUMN kategori VARCHAR(50) NOT NULL DEFAULT 'Diğer'
                """))
            
            db.session.commit()
        print("Veritabanı başarıyla güncellendi.")
    except Exception as e:
        db.session.rollback()
        print(f"Veritabanı güncellenirken hata oluştu: {e}")

def seed_database():
    """Örnek araçları veritabanına ekle"""
    try:
        # Örnek araçları ekle
        arabalar = [
            {
                'marka': 'BMW',
                'model': '320i',
                'yil': 2022,
                'gunluk_fiyat': 500,
                'resim_url': 'bmw-320i.jpg',
                'aciklama': 'Lüks ve konforlu BMW 320i',
                'kategori': 'Lüks'
            },
            {
                'marka': 'Mercedes',
                'model': 'C200',
                'yil': 2023,
                'gunluk_fiyat': 550,
                'resim_url': 'mercedes-c200.jpg',
                'aciklama': 'Şık ve modern Mercedes C200',
                'kategori': 'Lüks'
            },
            {
                'marka': 'Audi',
                'model': 'A4',
                'yil': 2022,
                'gunluk_fiyat': 480,
                'resim_url': 'audi-a4.jpg',
                'aciklama': 'Sportif ve dinamik Audi A4',
                'kategori': 'Lüks'
            },
            {
                'marka': 'Volkswagen',
                'model': 'Passat',
                'yil': 2023,
                'gunluk_fiyat': 400,
                'resim_url': 'volkswagen-passat.jpg',
                'aciklama': 'Ekonomik ve güvenilir VW Passat',
                'kategori': 'Orta Segment'
            },
            {
                'marka': 'Tesla',
                'model': 'Model X',
                'yil': 2023,
                'gunluk_fiyat': 800,
                'resim_url': 'Tesla-ModelX-2016-01.jpg',
                'aciklama': 'Elektrikli ve modern Tesla Model X',
                'kategori': 'Elektrikli'
            }
        ]
        
        # Araçları veritabanına ekle
        for araba_data in arabalar:
            araba = Araba(**araba_data)
            db.session.add(araba)
        
        db.session.commit()
        logging.info("Örnek araçlar başarıyla eklendi.")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Örnek araçlar eklenirken hata oluştu: {e}")
        raise e

def init_database():
    """Veritabanını başlat ve gerekli kontrolleri yap"""
    try:
        # Önce SQLAlchemy ile tabloları oluştur
        with app.app_context():
            db.create_all()
            logging.info("Veritabanı tabloları kontrol edildi/oluşturuldu.")
            
            # Veritabanı güncellemelerini yap
            update_database()
            
            # Admin kullanıcısını kontrol et ve yoksa oluştur
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    is_admin=True
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                logging.info("Admin kullanıcısı oluşturuldu.")
            
            # Örnek araçları kontrol et ve yoksa ekle
            if not Araba.query.first():
                seed_database()
                logging.info("Örnek araçlar eklendi.")
            
            logging.info("Veritabanı başlatma işlemi tamamlandı.")

    except Exception as e:
        logging.error(f"Veritabanı başlatılırken hata oluştu: {e}")
        raise e

def create_app():
    """Flask uygulamasını oluştur ve yapılandır"""
    try:
        # Upload klasörünü oluştur
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Veritabanını başlat
        init_database()
        
        return app
    except Exception as e:
        logging.error(f"Uygulama oluşturulurken hata oluştu: {e}")
        raise e

if __name__ == '__main__':
    try:
        app = create_app()
        app.run(host='0.0.0.0', port=8000, debug=False)
    except Exception as e:
        logging.error(f"Uygulama başlatılırken hata oluştu: {e}")
        raise e 
