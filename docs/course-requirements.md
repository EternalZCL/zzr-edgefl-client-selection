# 【中文题目】

面向云边协同场景的分布式人工智能感知与决策关键技术研究

# 【英文题目】

Research on Key Technologies for Distributed Artificial Intelligence Perception and Decision-Making in Cloud–Edge Collaborative Scenarios

# 【主要任务和目标】

随着人工智能、物联网和新一代移动通信技术的发展，智能计算正由传统云端集中处理向云、边、端协同架构演进。在工业制造、智慧交通、能源互联网和通信网络等场景中，大量终端设备持续产生多源异构数据，对实时感知、协同分析和自主决策提出了更高要求。然而，传统集中式人工智能系统依赖云端算力与网络连接，容易受到通信时延、带宽限制和数据隐私等因素影响；单一边缘节点又面临计算资源有限、环境信息不完整及局部决策难以兼顾全局目标等问题。因此，有必要研究云边协同环境下的分布式人工智能技术，实现多节点之间的协同感知、模型训练与联合决策。

本课题围绕“云边协同环境下多个智能节点如何实现高效感知与协同决策”开展研究。学生可选择智慧工厂设备监测、城市交通协同感知、6G 基站智能运维或无人机协同任务等具体场景，构建包含云端服务器、边缘计算节点和终端设备的分布式智能系统，研究有限计算与通信资源条件下的协同学习、任务调度和决策优化方法，提升系统的实时性、可靠性与任务执行效率。

本课题建议重点研究以下三类核心技术，学生可根据具体场景选择其中一个方向深入开展。

（1）分布式人工智能与多智能体协同决策技术。将边缘节点或终端设备抽象为具备局部感知与自主决策能力的智能体，通过多智能体系统（MAS）、协作通信和多智能体强化学习等方法，实现节点间的信息共享、任务分配与联合决策。重点研究局部信息不完整条件下的多节点协作机制，以及动态环境中的全局资源优化问题。

（2）联邦学习与分布式协同模型训练技术。针对多节点数据分散、隐私保护和通信资源受限等问题，研究联邦学习（FL）及分布式模型优化方法。可从 FedAvg 算法入手，实现“云端模型下发—边缘本地训练—模型更新上传—全局模型聚合”的协同训练流程，并进一步探索 FedProx、SCAFFOLD 等方法在数据异构和节点算力差异条件下的优化效果。

（3）云边协同推理与动态任务调度技术。针对云端与边缘节点算力、带宽和响应时延的差异，研究模型压缩、知识蒸馏、协同推理与动态任务卸载等技术。通过分析节点负载、网络状态和任务复杂度，设计合理的计算任务分配机制，实现本地快速响应与云端复杂计算之间的协同优化，降低系统推理时延与通信开销。

本课题可按照“场景选择—系统建模—算法设计—协同优化—实验验证”的流程开展。首先选定具体应用场景，分析不同节点的数据来源、计算资源和通信约束；随后构建云边协同系统模型，选择多智能体协作、联邦学习或动态任务调度等技术设计相应算法；最终利用 Python、PyTorch、Flower、Ray 等工具搭建仿真环境，与集中式处理或典型分布式方法进行对比，从感知准确率、任务完成率、响应时延、通信开销和资源占用等方面评价方法有效性，形成算法实现、实验结果与技术报告。

# 【对学生的要求】

计算机科学与技术、人工智能、软件工程、通信工程、自动化、电子信息、数学等相关专业学生均可参与。学生应具备一定的 Python 或 C/C++ 编程能力，了解机器学习、深度学习、计算机网络、分布式系统或强化学习中的至少一个方向，能够阅读相关英文文献并完成基础算法实现与实验分析。课题不要求同时掌握全部分布式人工智能技术，也不要求具备真实工业设备或通信网络环境，可通过公开数据集、仿真平台或轻量化原型系统开展研究。鼓励学生结合自身专业基础选择具体技术方向，完成具有一定创新性和可验证性的研究成果。

# 【参考文献】

[1] STONE P, VELOSO M. Multiagent Systems: A Survey from a Machine Learning Perspective[J]. Autonomous Robots, 2000, 8: 345–383.

[2] ZHANG K, YANG Z, BAŞAR T. Multi-Agent Reinforcement Learning: A Selective Overview of Theories and Algorithms[M]//Handbook of Reinforcement Learning and Control. 2021.

[3] MCMAHAN B, MOORE E, RAMAGE D, et al. Communication-Efficient Learning of Deep Networks from Decentralized Data[C]//AISTATS. 2017: 1273–1282.

[4] LI T, SAHU A K, ZAHEER M, et al. Federated Optimization in Heterogeneous Networks[C]//MLSys. 2020.

[5] ZHOU Z, CHEN X, LI E, et al. Edge Intelligence: Paving the Last Mile of Artificial Intelligence with Edge Computing[J]. Proceedings of the IEEE, 2019, 107(8): 1738–1762.

[6] LI E, ZHOU Z, CHEN X. Edge Intelligence: On-Demand Deep Learning Model Co-Inference with Device-Edge Synergy[C]//Proceedings of the Workshop on Mobile Edge Communications. 2018: 31–36.
