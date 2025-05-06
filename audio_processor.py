import os
import numpy as np
import librosa
import soundfile as sf
import logging
from scipy import signal

logger = logging.getLogger(__name__)

class AudioProcessor:
    """音频处理类，用于对齐原唱和伴奏音频"""
    
    def __init__(self):
        # self.sr = 22050  # 不再固定采样率
        self.hop_length = 512  # 跳跃长度，用于特征提取
    
    def align_audio(self, vocal_path, instrumental_path, output_path):
        """对齐原唱和伴奏音频
        
        Args:
            vocal_path: 原唱音频文件路径
            instrumental_path: 伴奏音频文件路径
            output_path: 输出文件路径
        """
        logger.info(f"开始处理: {os.path.basename(vocal_path)} 和 {os.path.basename(instrumental_path)}")
        
        try:
            # 加载音频文件，保留原始采样率和声道
            vocal, sr_vocal = librosa.load(vocal_path, sr=None, mono=False)
            instrumental, sr_inst = librosa.load(instrumental_path, sr=None, mono=False)
            
            # 获取原唱的原始信息
            vocal_info = sf.info(vocal_path)
            original_subtype = vocal_info.subtype
            original_channels = vocal_info.channels
            
            logger.info(f"原唱采样率: {sr_vocal}, 声道数: {original_channels}, 格式: {vocal_info.format}, 子类型: {original_subtype}")
            logger.info(f"伴奏采样率: {sr_inst}")
            
            # 确保数据是二维的 (channels, samples)
            if vocal.ndim == 1:
                vocal = vocal[np.newaxis, :]
            if instrumental.ndim == 1:
                instrumental = instrumental[np.newaxis, :]
                
            logger.info(f"原唱长度: {vocal.shape[1]/sr_vocal:.2f}秒, 伴奏长度: {instrumental.shape[1]/sr_inst:.2f}秒")
            
            # 提取特征 (使用单声道进行特征提取，但保留原始多声道数据)
            # 注意：如果采样率不同，特征提取和对齐可能不准确，这里假设对齐主要依赖节奏而非精确频率
            # 如果需要更精确对齐，可能需要先将两者重采样到同一采样率
            vocal_mono = librosa.to_mono(vocal)
            inst_mono = librosa.to_mono(instrumental)
            # 使用原唱的采样率进行特征提取
            vocal_features = self._extract_features(vocal_mono, sr_vocal)
            # 使用伴奏的采样率进行特征提取 (或者统一重采样后再提取)
            inst_features = self._extract_features(inst_mono, sr_inst)
            
            # 确定用于计算偏移量的采样率（例如，使用原唱的）
            sr_for_offset = sr_vocal
            
            # 计算时间偏移
            offset, confidence = self._find_offset(vocal_features, inst_features)
            offset_seconds = offset * self.hop_length / sr_for_offset # 使用计算特征时的采样率
            
            logger.info(f"检测到时间偏移: {offset_seconds:.3f}秒, 置信度: {confidence:.2f}")
            
            # 对齐音频 (使用原始多声道数据和采样率)
            # 目标长度应基于伴奏的样本数
            target_length_samples = instrumental.shape[1]
            aligned_vocal = self._apply_offset(vocal, offset, target_length_samples, sr_for_offset)
            
            # 保存对齐后的音频，使用原唱的采样率、声道数和尝试保留原始位深度
            # soundfile 会根据输出文件扩展名和 subtype 选择格式
            # 转置 aligned_vocal 使其形状为 (samples, channels) 以符合 soundfile 的要求
            sf.write(output_path, aligned_vocal.T, samplerate=sr_vocal, subtype=original_subtype)
            logger.info(f"已保存对齐后的音频: {output_path}")
            
            return offset_seconds, confidence, True
        
        except Exception as e:
            logger.error(f"处理音频时出错: {str(e)}")
            return 0.0, 0.0, False
    
    def _extract_features(self, audio, sr):
        """从音频中提取特征
        
        这里使用梅尔频谱图作为特征，也可以使用其他特征如MFCC
        """
        # 计算梅尔频谱图
        mel_spec = librosa.feature.melspectrogram(
            y=audio, # 确保输入是单声道
            sr=sr, # 使用传入的采样率
            n_mels=128, 
            hop_length=self.hop_length
        )
        
        # 转换为分贝单位
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
        
        return mel_spec_db
    
    def _find_offset(self, vocal_features, inst_features):
        """使用互相关来找到两个音频之间的时间偏移"""
        # 对特征进行降维，取平均值
        vocal_mean = np.mean(vocal_features, axis=0)
        inst_mean = np.mean(inst_features, axis=0)
        
        # 计算互相关
        correlation = signal.correlate(inst_mean, vocal_mean, mode='full')
        
        # 找到最大相关性的位置
        max_idx = np.argmax(correlation)
        offset = max_idx - (len(vocal_mean) - 1)
        
        # 计算置信度 (归一化的相关系数)
        confidence = correlation[max_idx] / np.sqrt(np.sum(vocal_mean**2) * np.sum(inst_mean**2))
        
        return offset, confidence
    
    def _apply_offset(self, vocal, offset, target_length_samples, sr):
        """应用时间偏移到原唱音频
        
        Args:
            vocal: 原唱音频数据
            offset: 帧偏移量 (正值表示原唱需要向右移动，负值表示向左移动)
            target_length: 目标长度 (通常是伴奏的长度)
            
        Returns:
            对齐后的原唱音频
        """
        # 转换帧偏移为样本偏移 (使用计算偏移时的采样率)
        sample_offset = int(offset * self.hop_length)
        
        # 创建一个目标形状的空数组 (channels, samples)
        num_channels = vocal.shape[0]
        aligned = np.zeros((num_channels, target_length_samples))
        
        if sample_offset >= 0:
            # 原唱需要向右移动 (开始晚于伴奏)
            # 原唱需要向右移动 (开始晚于伴奏)
            # 注意：vocal.shape[1] 是样本数
            src_start = 0
            src_len = min(vocal.shape[1], target_length_samples - sample_offset)
            src_end = src_start + src_len
            dst_start = sample_offset
            dst_end = dst_start + src_len
        else:
            # 原唱需要向左移动 (开始早于伴奏)
            src_start = -sample_offset
            src_len = min(vocal.shape[1] + sample_offset, target_length_samples)
            src_end = src_start + src_len
            dst_start = 0
            dst_end = dst_start + src_len
        
        # 复制有效部分 (处理多声道)
        if src_len > 0 and dst_end > dst_start:
            aligned[:, dst_start:dst_end] = vocal[:, src_start:src_end]
        
        return aligned
    
    def _stretch_audio(self, audio, factor):
        """拉伸或压缩音频
        
        Args:
            audio: 音频数据
            factor: 拉伸因子 (>1表示拉长，<1表示压缩)
            
        Returns:
            拉伸后的音频
        """
        return librosa.effects.time_stretch(audio, rate=factor)