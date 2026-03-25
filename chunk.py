import re
from modelscope import AutoTokenizer

# Default model path
DEFAULT_MODEL_PATH = r"C:\Users\z1881\Downloads\graph encoder\qwen3-0.6b"

def chunk_text(text, chunk_size, model_path=DEFAULT_MODEL_PATH, tokenizer=None):
    """
    将输入文本按照指定的token数量进行切片。
    逻辑：
    1. 先按标点符号（。？！.?!）分句，保留标点。
    2. 计算每一句的token数。
    3. 累积句子直到达到chunk_size上限。
    4. 如果当前chunk放不下新的一句，则开启新的chunk。

    Args:
        text (str): 输入文本。
        chunk_size (int): 每段的token数量上限。
        model_path (str): 模型路径，用于加载tokenizer。
        tokenizer (AutoTokenizer, optional): 预加载的tokenizer实例。

    Returns:
        list: 切片后的文本列表。
    """
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(model_path)
    
    # 1. 按标点符号分句，保留标点
    # 使用捕获组 () 保留分隔符，使用 []+ 匹配连续的标点
    parts = re.split(r'([。？！.?!]+)', text)
    
    sentences = []
    current_sent = ""
    # 重新组合文本和标点
    for part in parts:
        current_sent += part
        # 如果当前部分包含标点（通常是分隔符部分），则认为是一个句子的结束
        if re.search(r'[。？！.?!]', part):
            sentences.append(current_sent)
            current_sent = ""
    
    # 处理剩余的文本（末尾没有标点的情况）
    if current_sent:
        sentences.append(current_sent)
        
    chunks = []
    current_chunk_ids = []
    current_chunk_len = 0
    
    for sent in sentences:
        # 计算当前句子的token
        sent_ids = tokenizer.encode(sent, add_special_tokens=False)
        sent_len = len(sent_ids)
        
        # 判断加入当前句子后是否会超过 chunk_size
        if current_chunk_len + sent_len <= chunk_size:
            # 没有超过，继续延长当前 chunk
            current_chunk_ids.extend(sent_ids)
            current_chunk_len += sent_len
        else:
            # 超过了，先保存当前的 chunk（如果有内容）
            if current_chunk_ids:
                chunks.append(tokenizer.decode(current_chunk_ids, skip_special_tokens=True))
            
            # 重新开始下一个 chunk
            # 这里需要处理一种特殊情况：如果单句长度本身就超过了 chunk_size
            if sent_len > chunk_size:
                # 策略：强制切分这个超长句子
                for i in range(0, sent_len, chunk_size):
                    sub_ids = sent_ids[i : i + chunk_size]
                    if len(sub_ids) == chunk_size:
                        # 满额的一个 chunk
                        chunks.append(tokenizer.decode(sub_ids, skip_special_tokens=True))
                    else:
                        # 剩下的部分作为新的当前 chunk 的开始
                        current_chunk_ids = sub_ids
                        current_chunk_len = len(sub_ids)
            else:
                # 单句长度正常，直接作为新 chunk 的开始
                current_chunk_ids = sent_ids
                current_chunk_len = sent_len
                
    # 保存最后一个 chunk
    if current_chunk_ids:
        chunks.append(tokenizer.decode(current_chunk_ids, skip_special_tokens=True))
        
    return chunks

if __name__ == "__main__":
    # 示例用法
    sample_text = (
        "这是第一句完整的话。" 
        "This is a sentence in English. "
        "这是一个非常非常长的句子，用来测试当句子长度超过限制时会发生什么情况，"
        "理论上它应该会被强制切分，因为我们不能让它无限长下去，"
        "但是我们希望在可能的情况下尽量保持句子的完整性。" 
        "Short sentence! "
        "Are you okay? "
        "好的！"
    )
    
    # 设置较小的 chunk_size 以观察切分效果
    size = 20 
    
    print(f"原始文本长度: {len(sample_text)}")
    print(f"目标 chunk_size: {size}")
    
    try:
        result = chunk_text(sample_text, size)
        print(f"\n切分结果 (共 {len(result)} 段):")
        for idx, chunk in enumerate(result):
            print(f"---\n片段 {idx+1} (len={len(chunk)}):\n{chunk}")
        print("---")
    except Exception as e:
        print(f"运行出错: {e}")
