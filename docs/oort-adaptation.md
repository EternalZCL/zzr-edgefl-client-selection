# Oort 适配来源与边界

本研究是独立编写的30客户端CPU适配，不复制作者分布式系统，也不声称是作者实现的精确复现。

- 论文：Lai et al., *Oort: Efficient Federated Learning via Guided Participant Selection*, OSDI 2021，https://www.usenix.org/conference/osdi21/presentation/lai 。
- 阅读的作者代码路径：SymbioticLab/Oort/oort/oort.py。
- 该路径当前最后修改commit：f5fccf35090ed4725a65b18dcefc45aba627c1a7；永久链接：https://github.com/SymbioticLab/Oort/blob/f5fccf35090ed4725a65b18dcefc45aba627c1a7/oort/oort.py 。
- 保留：训练RMS效用、截断、历史不确定度、速度惩罚、加权利用、探索和pacer。
- 区别：效用来自已付费训练minibatch而非额外全数据扫描；只模拟30用户和同步轮次；预热后仍保留均匀探索；不确定度按模拟时间陈旧度；固定探索比例与简化pacer，未复现大规模集群全部过滤/黑名单机制。
- 等客户端效用移除样本量系数；原始效用保留样本量，两者各配置都进入同级筛选，最多8组，不根据最终测试选择。

因此，最终结论只适用于这份有限适配及当前HAPT协议，不能据此声称超过完整原版Oort或整个客户端选择研究领域。
