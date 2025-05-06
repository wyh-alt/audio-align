import os
import sys
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog, QProgressBar,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from audio_processor import AudioProcessor

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DropLineEdit(QLineEdit):
    """支持拖放功能的输入框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.setText(urls[0].toLocalFile())
            event.acceptProposedAction()


class ProcessingThread(QThread):
    """处理音频的线程"""
    update_signal = pyqtSignal(str)  # 用于更新UI的信号
    progress_signal = pyqtSignal(int)  # 进度信号
    finished_signal = pyqtSignal()  # 完成信号
    result_signal = pyqtSignal(str, str, float, float, bool)  # 处理结果信号(原唱,伴奏,时间偏移,置信度,对齐结果)

    def __init__(self, vocal_dir, instrumental_dir, output_dir, output_format="{id}-原唱"):
        super().__init__()
        self.vocal_dir = vocal_dir
        self.instrumental_dir = instrumental_dir
        self.output_dir = output_dir
        self.output_format = output_format
        self.is_running = True

    def run(self):
        try:
            processor = AudioProcessor()
            # 获取所有音频文件
            vocal_files = self._get_audio_files(self.vocal_dir)
            instrumental_files = self._get_audio_files(self.instrumental_dir)
            
            # 创建输出目录
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                
            # 匹配文件
            matched_pairs = self._match_files(vocal_files, instrumental_files)
            total_pairs = len(matched_pairs)
            
            self.update_signal.emit(f"找到 {total_pairs} 对匹配的音频文件")
            
            # 处理每一对匹配的文件
            for i, (vocal_file, instrumental_file) in enumerate(matched_pairs):
                if not self.is_running:
                    self.update_signal.emit("处理已停止")
                    break
                    
                self.update_signal.emit(f"处理 {os.path.basename(vocal_file)} 和 {os.path.basename(instrumental_file)}")
                
                # 获取文件ID和扩展名
                filename = os.path.basename(vocal_file)
                file_id = filename.split('-')[0].strip() if '-' in filename else ''
                file_ext = os.path.splitext(filename)[1]
                
                # 生成输出文件名
                output_filename = self.output_format.format(id=file_id) + file_ext
                output_file = os.path.join(self.output_dir, output_filename)
                
                # 处理音频对齐
                time_offset, confidence, aligned = processor.align_audio(vocal_file, instrumental_file, output_file)
                
                # 发送处理结果信号
                self.result_signal.emit(
                    os.path.basename(vocal_file),
                    os.path.basename(instrumental_file),
                    time_offset,
                    confidence,
                    aligned
                )
                
                self.update_signal.emit(f"已保存对齐后的文件: {output_file}")
                self.progress_signal.emit(int((i + 1) / total_pairs * 100))
            
            if self.is_running:
                self.update_signal.emit("所有文件处理完成！")
                self.finished_signal.emit()
                
        except Exception as e:
            self.update_signal.emit(f"错误: {str(e)}")
            logger.error(f"处理过程中出错: {str(e)}")
    
    def stop(self):
        self.is_running = False
        self.update_signal.emit("正在停止处理...")
        self.finished_signal.emit()  # 发送完成信号以重置UI状态
    
    def _get_audio_files(self, directory):
        """获取目录中的所有音频文件"""
        audio_extensions = [".mp3", ".wav", ".flac", ".ogg", ".m4a"]
        audio_files = []
        
        for file in os.listdir(directory):
            if any(file.lower().endswith(ext) for ext in audio_extensions):
                audio_files.append(os.path.join(directory, file))
                
        return audio_files
    
    def _match_files(self, vocal_files, instrumental_files):
        """根据文件名中的ID匹配原唱和伴奏文件
        支持字母数字组合的ID格式，如'YPDJP029'
        """
        matched_pairs = []
        vocal_dict = {}
        
        # 从文件名中提取ID
        for vocal_file in vocal_files:
            filename = os.path.basename(vocal_file)
            # 提取文件名中'-'前的部分作为ID，支持字母数字组合
            if '-' in filename:
                file_id = filename.split('-')[0].strip()
                # 确保ID不为空且只包含字母和数字
                if file_id and file_id.replace(' ', '').isalnum():
                    vocal_dict[file_id] = vocal_file
        
        # 匹配伴奏文件
        for inst_file in instrumental_files:
            filename = os.path.basename(inst_file)
            if '-' in filename:
                file_id = filename.split('-')[0].strip()
                # 确保ID不为空且只包含字母和数字
                if file_id and file_id.replace(' ', '').isalnum() and file_id in vocal_dict:
                    matched_pairs.append((vocal_dict[file_id], inst_file))
                    self.update_signal.emit(f"匹配到: ID={file_id}, 原唱={os.path.basename(vocal_dict[file_id])}, 伴奏={os.path.basename(inst_file)}")
        
        return matched_pairs


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.processing_thread = None
    
    def init_ui(self):
        self.setWindowTitle("原唱伴奏对齐工具")
        self.setGeometry(100, 100, 800, 600)
        
        # 主布局
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # 原唱路径选择
        vocal_layout = QHBoxLayout()
        vocal_label = QLabel("原唱路径:")
        self.vocal_path = DropLineEdit()
        vocal_btn = QPushButton("浏览...")
        vocal_btn.clicked.connect(lambda: self.browse_folder(self.vocal_path))
        vocal_layout.addWidget(vocal_label)
        vocal_layout.addWidget(self.vocal_path)
        vocal_layout.addWidget(vocal_btn)
        
        # 伴奏路径选择
        inst_layout = QHBoxLayout()
        inst_label = QLabel("伴奏路径:")
        self.inst_path = DropLineEdit()
        inst_btn = QPushButton("浏览...")
        inst_btn.clicked.connect(lambda: self.browse_folder(self.inst_path))
        inst_layout.addWidget(inst_label)
        inst_layout.addWidget(self.inst_path)
        inst_layout.addWidget(inst_btn)
        
        # 输出路径选择
        output_layout = QHBoxLayout()
        output_label = QLabel("输出路径:")
        self.output_path = DropLineEdit()
        output_btn = QPushButton("浏览...")
        output_btn.clicked.connect(lambda: self.browse_folder(self.output_path))
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_btn)
        
        # 输出文件命名格式
        format_layout = QHBoxLayout()
        format_label = QLabel("输出文件命名格式:")
        self.format_input = QLineEdit()
        self.format_input.setPlaceholderText("{id}-原唱")
        self.format_input.setText("{id}-原唱")
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_input)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始处理")
        self.stop_btn = QPushButton("停止处理")
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        # 结果表格
        result_label = QLabel("处理结果:")
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(5)
        self.result_table.setHorizontalHeaderLabels(["原唱", "伴奏", "时间偏移(秒)", "置信度", "对齐结果"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # 导出按钮
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self.export_results)
        self.export_btn.setEnabled(False)
        btn_layout.addWidget(self.export_btn)
        
        # 添加所有组件到主布局
        main_layout.addLayout(vocal_layout)
        main_layout.addLayout(inst_layout)
        main_layout.addLayout(output_layout)
        main_layout.addLayout(format_layout)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(result_label)
        main_layout.addWidget(self.result_table)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
    
    def browse_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            line_edit.setText(folder)
    
    def log_message(self, message):
        print(message)  # 改为控制台输出
        
    def add_result(self, vocal_file, inst_file, time_offset, confidence, aligned):
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        
        self.result_table.setItem(row, 0, QTableWidgetItem(vocal_file))
        self.result_table.setItem(row, 1, QTableWidgetItem(inst_file))
        self.result_table.setItem(row, 2, QTableWidgetItem(f"{time_offset:.2f}"))
        self.result_table.setItem(row, 3, QTableWidgetItem(f"{confidence:.2%}"))
        self.result_table.setItem(row, 4, QTableWidgetItem("成功" if aligned else "失败"))
        
    def export_results(self):
        if self.result_table.rowCount() == 0:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出结果",
            "",
            "Excel Files (*.xlsx);;All Files (*)"
        )
        
        if not file_path:
            return
            
        try:
            import pandas as pd
            
            # 收集表格数据
            data = []
            for row in range(self.result_table.rowCount()):
                row_data = []
                for col in range(self.result_table.columnCount()):
                    item = self.result_table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)
            
            # 创建DataFrame并导出
            df = pd.DataFrame(
                data,
                columns=["原唱", "伴奏", "时间偏移(秒)", "置信度", "对齐结果"]
            )
            df.to_excel(file_path, index=False)
            
            self.log_message(f"结果已导出到: {file_path}")
            
        except Exception as e:
            self.log_message(f"导出失败: {str(e)}")
    
    def start_processing(self):
        vocal_dir = self.vocal_path.text()
        inst_dir = self.inst_path.text()
        output_dir = self.output_path.text()
        
        # 验证输入
        if not vocal_dir or not os.path.isdir(vocal_dir):
            self.log_message("错误: 请选择有效的原唱文件夹")
            return
        
        if not inst_dir or not os.path.isdir(inst_dir):
            self.log_message("错误: 请选择有效的伴奏文件夹")
            return
        
        if not output_dir:
            self.log_message("错误: 请选择输出文件夹")
            return
        
        # 更新UI状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_message("开始处理...")
        
        # 获取输出文件命名格式
        output_format = self.format_input.text() or "{id}-原唱"
        
        # 创建并启动处理线程
        self.processing_thread = ProcessingThread(vocal_dir, inst_dir, output_dir, output_format)
        self.processing_thread.update_signal.connect(self.log_message)
        self.processing_thread.progress_signal.connect(self.progress_bar.setValue)
        self.processing_thread.finished_signal.connect(self.processing_finished)
        self.processing_thread.result_signal.connect(self.add_result)
        self.result_table.setRowCount(0)  # 清空表格
        self.processing_thread.start()
    
    def stop_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.log_message("已发送停止信号，等待当前处理完成...")
    
    def processing_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.log_message("处理完成")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())