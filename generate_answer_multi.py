from html import entities
from transformers import AutoTokenizer
import torch
import os
import sys
import json
from tqdm import tqdm
sys.path.append("../../")
from component.utils import ModelUtils
"""
单轮对话，不具有对话历史的记忆功能
"""


def main():
    # 使用合并后的模型进行推理
    # model_name_or_path = '/home/sda/xuguangtao/Firefly-master/checkpoint/firefly-qwen-7b-qlora-sft-merge'
    # adapter_name_or_path = None

    # 使用base model和adapter进行推理，无需手动合并权重
    model_name_or_path = '/root/firefly/Qwen/Qwen-7B'
    adapter_name_or_path = '/root/firefly/checkpoint-8705'

    # 是否使用4bit进行推理，能够节省很多显存，但效果可能会有一定的下降
    load_in_4bit = False
    # 生成超参配置
    max_new_tokens = 500
    history_max_len = 1000
    top_p = 0.9
    temperature = 0.35
    repetition_penalty = 1.0
    device = 'cuda'
    # 加载模型
    model = ModelUtils.load_model(
        model_name_or_path,
        load_in_4bit=load_in_4bit,
        adapter_name_or_path=adapter_name_or_path
    ).eval()
    tokenizer = AutoTokenizer.from_pretrained(
        model_name_or_path,
        trust_remote_code=True,
        # llama不支持fast
        use_fast=False if model.config.model_type == 'llama' else True
    )
    # QWenTokenizer比较特殊，pad_token_id、bos_token_id、eos_token_id均为None。eod_id对应的token为<|endoftext|>
    if tokenizer.__class__.__name__ == 'QWenTokenizer':
        tokenizer.pad_token_id = tokenizer.eod_id
        tokenizer.bos_token_id = tokenizer.eod_id
        tokenizer.eos_token_id = tokenizer.eod_id

    with open('/root/firefly/data/test/MRD_testset.jsonl', 'r', encoding='utf8') as f:
        lines = f.readlines()
        new_datas = []
        for line in tqdm(lines):
            data = json.loads(line)
            new_data = data
            history_token_ids = torch.tensor([[tokenizer.bos_token_id]], dtype=torch.long)
            for id, dialoge in enumerate(data['conversation']):
                text = dialoge['human']
                input_ids = tokenizer(text, return_tensors="pt", add_special_tokens=False).input_ids
                eos_token_id = torch.tensor([[tokenizer.eos_token_id]], dtype=torch.long)
                user_input_ids = torch.concat([input_ids, eos_token_id], dim=1)
                history_token_ids = torch.concat((history_token_ids, user_input_ids), dim=1)
                model_input_ids = history_token_ids[:, -history_max_len:].to(device)
                with torch.no_grad():
                    outputs = model.generate(
                        input_ids=model_input_ids, max_new_tokens=max_new_tokens, do_sample=True,
                        top_p=top_p, temperature=temperature, repetition_penalty=repetition_penalty,
                        eos_token_id=tokenizer.eos_token_id
                    )

                model_input_ids_len = model_input_ids.size(1)
                response_ids = outputs[:, model_input_ids_len:]
                history_token_ids = torch.concat((history_token_ids, response_ids.cpu()), dim=1)
                response = tokenizer.batch_decode(response_ids)
                response = response[0].strip().replace(tokenizer.eos_token, "")
                print('input:', text)
                print('output:', response)
                new_data['conversation'][id]['assistant'] = response
            new_datas.append(new_data)
    with open('/root/firefly/data/test/MRD_testset_answer.jsonl', 'w', encoding='utf8') as f:
        for data in new_datas:
            json.dump(data, f, ensure_ascii=False)
            f.write('\n')

if __name__ == '__main__':
    main()
