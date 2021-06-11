import tensorflow as tf
import numpy as np
import random
import tensorflow.contrib.layers as layers
from tqdm import tqdm
import time
import lstmmodel
import random
import tqdm

import os

os.environ['CUDA_VISIBLE_DEVICES'] = '/cpu:0'


class environment():

    def __init__(self, sentence_len):
        self.sentence_len = sentence_len

    # 句子信息 batch 当前步 重置，返回当前state
    def reset(self, e1, e2, batch_sentence_ebd, batch_reward):
        self.id_e1 = e1
        self.id_e2 = e2
        self.batch_reward = batch_reward
        self.batch_len = len(batch_sentence_ebd)
        self.sentence_ebd = batch_sentence_ebd
        self.current_step = 0
        self.num_selected = 0
        self.current_step = 0
        self.list_selected = []
        self.vector_current = self.sentence_ebd[self.current_step]
        self.vector_mean = np.array([0.0 for x in range(self.sentence_len)], dtype=np.float32)
        self.vector_sum = np.array([0.0 for x in range(self.sentence_len)], dtype=np.float32)

        current_state = [self.vector_current, self.vector_mean, self.id_e1, self.id_e2]
        return current_state

    def step(self, action):

        if action == 1:
            self.num_selected += 1
            self.list_selected.append(self.current_step)

        self.vector_sum = self.vector_sum + action * self.vector_current
        if self.num_selected == 0:
            self.vector_mean = np.array([0.0 for x in range(self.sentence_len)], dtype=np.float32)
        else:
            self.vector_mean = self.vector_sum / self.num_selected

        self.current_step += 1

        if (self.current_step < self.batch_len):
            self.vector_current = self.sentence_ebd[self.current_step]

        current_state = [self.vector_current, self.vector_mean, self.id_e1, self.id_e2]
        return current_state

    def reward(self):
        assert (len(self.list_selected) == self.num_selected)
        reward = [self.batch_reward[x] for x in self.list_selected]
        reward = np.array(reward)
        reward = np.mean(reward)
        return reward


def get_action(prob):

    tmp = prob[0]
    result = np.random.rand()
    if result>0 and result< tmp:
        return 1
    elif result >=tmp and result<1:
        return 0

def decide_action(prob):
    tmp = prob[0]
    if tmp>=0.5:
        return 1
    elif tmp < 0.5:
        return 0


class agent():
    def __init__(self, lr, entity_ebd, s_size):

        # get action
        entity_embedding = tf.get_variable(name='entity_embedding', initializer=entity_ebd, trainable=False)

        # 输入
        self.state_in = tf.placeholder(shape=[None, s_size], dtype=tf.float32)  # 输入state
        self.entity1 = tf.placeholder(dtype=tf.int32, shape=[None], name='entity1')
        self.entity2 = tf.placeholder(dtype=tf.int32, shape=[None], name='entity2')

        # 在entity_embedding 找到ids=entity1 的张量(实体嵌入)
        self.entity1_ebd = tf.nn.embedding_lookup(entity_embedding, self.entity1)
        self.entity2_ebd = tf.nn.embedding_lookup(entity_embedding, self.entity2)

        # 将三个输入整合到一个输入
        # shape=[[state_in[0],entity_ebd[0]],[],.....]
        '''
            t1 = [[1, 2, 3], [4, 5, 6]]
            t2 = [[7, 8, 9], [10, 11, 12]]
            tf.concat(axis=1, values=[t1, t2])  # [[1, 2, 3, 7, 8, 9], [4, 5, 6, 10, 11, 12]]

        '''
        # 输入
        self.input = tf.concat(axis=1, values=[self.state_in, self.entity1_ebd, self.entity2_ebd])

        # self.input = tf.clip_by_value(tf.nn.sigmoid(self.input), 1e-5, 1)

        # #fc1
        # layer = tf.layers.dense(
        #     inputs=self.input,
        #     units=10,  # 输出个数
        #     activation=tf.nn.sigmoid,  # 激励函数
        #     kernel_initializer=tf.random_normal_initializer(mean=0, stddev=0.3),
        #     bias_initializer=tf.constant_initializer(0.1),
        #     name='fc1'
        # )
        # # fc2
        # all_act = tf.layers.dense(
        #     inputs=layer,
        #     units=1,  # 输出个数
        #     activation=None,  # 之后再加 Softmax
        #     kernel_initializer=tf.random_normal_initializer(mean=0, stddev=0.3),
        #     bias_initializer=tf.constant_initializer(0.1),
        #     name='fc2'
        # )
        # self.prob = tf.nn.softmax(all_act, name='act_prob')
        # self.prob = tf.reshape(self.prob, [-1])
        # reshape(tensor,[-1]) 将tensor变为1维的tensor
        '''
            t = [[1,1,2]
                 [2,2,3]]
            t 是[2x3]的tensor
            tf.reshape(t,[-1])=[1,1,2,2,2,3]
        '''
        # fully_connected 计算
        # arg input = input output=1 activation_fn=tf.nn.sigmoid //激活函数
        '''
            一层全连接层神经网络
        '''
        # input_normal = tf.layers.batch_normalization(self.input) # 正规化输入
        self.prob = tf.reshape(layers.fully_connected(self.input, 1, tf.nn.sigmoid), [-1])
        # compute loss
        '''
            获取当前的奖励和动作
        '''
        self.reward_holder = tf.placeholder(shape=[None], dtype=tf.float32)  # 奖励
        self.action_holder = tf.placeholder(shape=[None], dtype=tf.float32)  # 动作

        # the probability of choosing 0 or 1
        # 策略函数计算action的值
        self.pi = self.action_holder * self.prob + (1 - self.action_holder) * (1 - self.prob)

        # loss
        # 参数更新
        self.loss = -tf.reduce_sum(tf.log(self.pi) * self.reward_holder)

        # minimize loss
        optimizer = tf.train.AdamOptimizer(lr)
        self.train_op = optimizer.minimize(self.loss)

        # 获得参数的复制
        self.tvars = tf.trainable_variables()

        # manual update parameters
        self.tvars_holders = []
        for idx, var in enumerate(self.tvars):
            placeholder = tf.placeholder(tf.float32, name=str(idx) + '_holder')
            self.tvars_holders.append(placeholder)

        # 要跟新的参数列表
        self.update_tvar_holder = []
        for idx, var in enumerate(self.tvars):
            update_tvar = tf.assign(var, self.tvars_holders[idx])
            self.update_tvar_holder.append(update_tvar)

        '''
            根据梯度更新参数
        '''
        # compute gradient
        self.gradients = tf.gradients(self.loss, self.tvars)

        # update parameters using gradient
        self.gradient_holders = []
        for idx, var in enumerate(self.tvars):
            placeholder = tf.placeholder(tf.float32, name=str(idx) + '_holder')
            self.gradient_holders.append(placeholder)

        self.update_batch = optimizer.apply_gradients(zip(self.gradient_holders, self.tvars))


def train():
    # 加载数据
    train_entitypair = np.load('./data/train_entitypair.npy', allow_pickle=True)  #
    all_sentence_ebd = np.load('./data/all_sentence_ebd.npy', allow_pickle=True)
    all_reward = np.load('./data/all_reward.npy', allow_pickle=True)
    average_reward = np.load('data/average_reward.npy', allow_pickle=True)  # 平均奖励 = -1.3636588
    entity_ebd = np.load('origin_data/entity_ebd.npy', allow_pickle=True)  # 实体嵌入

    # 创建计算图
    g_rl = tf.Graph()

    # 在rl计算图上进行session的运行
    sess2 = tf.Session(graph=g_rl)

    # 创建环境 句子长度230
    env = environment(230)

    # 两个session
    with g_rl.as_default():
        with sess2.as_default():

            # 创建代理 agent learning rate=0.03 实体嵌入 state-size=460
            myAgent = agent(0.02, entity_ebd, 460)
            updaterate = 1
            num_epoch = 10
            sampletimes = 3
            best_reward = -100000

            init = tf.global_variables_initializer()
            sess2.run(init)
            saver = tf.train.Saver()
            # saver.restore(sess2, save_path='rlmodel/rl.ckpt')
            # graph 图展示模型结构
            # tf.summary.FileWriter("D://tensor_logs/", sess2.graph)
            '''
                tvars_best,tvars_old 和 gradbuffer ?
            '''
            tvars_best = sess2.run(myAgent.tvars)
            for index, var in enumerate(tvars_best):
                tvars_best[index] = var * 0

            tvars_old = sess2.run(myAgent.tvars)

            gradBuffer = sess2.run(myAgent.tvars)
            for index, grad in enumerate(gradBuffer):
                gradBuffer[index] = grad * 0

            g_rl.finalize()

            for epoch in range(num_epoch):

                all_list = list(range(len(all_sentence_ebd)))
                total_reward = []

                # shuffle bags 打乱bags中句子的顺序
                random.shuffle(all_list)

                # 每个bag为一个batch
                for batch in tqdm.tqdm(all_list):
                    # for batch in tqdm.tqdm(range(10000)):

                    batch_en1 = train_entitypair[batch][0]
                    batch_en2 = train_entitypair[batch][1]
                    batch_sentence_ebd = all_sentence_ebd[batch]
                    batch_reward = all_reward[batch]
                    batch_len = len(batch_sentence_ebd)

                    list_list_state = []
                    list_list_action = []
                    list_list_reward = []
                    avg_reward = 0

                    # add sample times
                    for j in range(sampletimes):
                        # reset environment 刷新环境 类似于env.render()
                        # 获得初始状态
                        state = env.reset(batch_en1, batch_en2, batch_sentence_ebd, batch_reward)
                        list_action = []
                        list_state = []
                        old_prob = []

                        # get action 获取动作
                        # start = time.time()
                        for i in range(batch_len):
                            state_in = np.append(state[0], state[1])
                            feed_dict = {}
                            feed_dict[myAgent.entity1] = [state[2]]
                            feed_dict[myAgent.entity2] = [state[3]]
                            feed_dict[myAgent.state_in] = [state_in]

                            prob = sess2.run(myAgent.prob, feed_dict=feed_dict)
                            old_prob.append(prob[0])
                            action = get_action(prob)  # 随机选择动作 0 或者 1
                            if action is None:
                                print(123)
                                action = 1
                            # add produce data for training cnn model
                            list_action.append(action)
                            list_state.append(state)
                            state = env.step(action)  #
                        # end = time.time()
                        # print ('get action:',end - start)
                        #
                        if env.num_selected == 0:
                            tmp_reward = average_reward
                        else:
                            tmp_reward = env.reward()

                        avg_reward += tmp_reward  # 计算batch_len中所有奖励
                        list_list_state.append(list_state)
                        list_list_action.append(list_action)
                        list_list_reward.append(tmp_reward)

                    avg_reward = avg_reward / sampletimes  # 计算batch_len中平均奖励

                    # add sample times
                    for j in range(sampletimes):

                        list_state = list_list_state[j]
                        list_action = list_list_action[j]
                        reward = list_list_reward[j]

                        # compute gradient 计算梯度
                        # start = time.time()
                        list_reward = [reward - avg_reward for x in range(batch_len)]
                        list_state_in = [np.append(state[0], state[1]) for state in list_state]
                        list_entity1 = [state[2] for state in list_state]
                        list_entity2 = [state[3] for state in list_state]

                        feed_dict = {}
                        feed_dict[myAgent.state_in] = list_state_in
                        feed_dict[myAgent.entity1] = list_entity1
                        feed_dict[myAgent.entity2] = list_entity2

                        '''
                            reward
                        '''

                        feed_dict[myAgent.reward_holder] = list_reward
                        feed_dict[myAgent.action_holder] = list_action

                        grads = sess2.run(myAgent.gradients, feed_dict=feed_dict)
                        # 将本次的梯度添加到梯度缓存
                        for index, grad in enumerate(grads):
                            gradBuffer[index] += grad
                        # end = time.time()
                        # print('get loss and update:', end - start)
                    # decide action and compute reward
                    state = env.reset(batch_en1, batch_en2, batch_sentence_ebd, batch_reward)

                    '''
                        根据state选择action 并计算reward
                    '''
                    old_prob = []
                    for i in range(batch_len):
                        state_in = np.append(state[0], state[1])
                        feed_dict = {}
                        feed_dict[myAgent.entity1] = [state[2]]
                        feed_dict[myAgent.entity2] = [state[3]]
                        feed_dict[myAgent.state_in] = [state_in]
                        prob = sess2.run(myAgent.prob, feed_dict=feed_dict)
                        old_prob.append(prob[0])
                        action = decide_action(prob)
                        state = env.step(action)
                    chosen_reward = [batch_reward[x] for x in env.list_selected]
                    total_reward += chosen_reward

                # apply gradient 更新梯度
                feed_dict = dictionary = dict(zip(myAgent.gradient_holders, gradBuffer))
                sess2.run(myAgent.update_batch, feed_dict=feed_dict)
                # 清空梯度缓存
                for index, grad in enumerate(gradBuffer):
                    gradBuffer[index] = grad * 0

                # get tvars_new 在梯度更新之后 获取最新参数
                tvars_new = sess2.run(myAgent.tvars)

                '''
                update old variables of the target network  更新target网络的参数
                使用policy gradients 方式
                '''
                tvars_update = sess2.run(myAgent.tvars)
                # 根据update rate更新target网络的参数  updaterate为 1
                for index, var in enumerate(tvars_update):
                    tvars_update[index] = updaterate * tvars_new[index] + (1 - updaterate) * tvars_old[index]

                feed_dict = dictionary = dict(zip(myAgent.tvars_holders, tvars_update))
                sess2.run(myAgent.update_tvar_holder, feed_dict)
                tvars_old = sess2.run(myAgent.tvars)  # ? 用于以后的更新
                # break

                ''''
                    根据奖励 获取最优参数
                '''
                # find the best parameters 获取最优参数
                chosen_size = len(total_reward)
                total_reward = np.mean(np.array(total_reward))  # 计算本回合的总奖励
                # 根据总奖励是否比最好奖励好，更新best_reward和tvars_best
                if (total_reward > best_reward):
                    best_reward = total_reward
                    tvars_best = tvars_old
                print('chosen sentence size:', chosen_size)
                print('total_reward:', total_reward)
                print('best_reward', best_reward)

            # set parameters = best_tvars 设置参数为 tvars_best
            feed_dict = dictionary = dict(zip(myAgent.tvars_holders, tvars_best))
            sess2.run(myAgent.update_tvar_holder, feed_dict)
            # save model
            saver.save(sess2, save_path='rlmodel/origin_rl_model.ckpt')


def select(save_path):
    train_word = np.load('./data/train_word.npy', allow_pickle=True)
    train_pos1 = np.load('./data/train_pos1.npy', allow_pickle=True)
    train_pos2 = np.load('./data/train_pos2.npy', allow_pickle=True)
    train_entitypair = np.load('./data/train_entitypair.npy', allow_pickle=True)
    y_train = np.load('data/train_y.npy', allow_pickle=True)

    all_sentence_ebd = np.load('./data/all_sentence_ebd.npy', allow_pickle=True)
    all_reward = np.load('./data/all_reward.npy', allow_pickle=True)
    entity_ebd = np.load('origin_data/entity_ebd.npy', allow_pickle=True)

    selected_word = []
    selected_pos1 = []
    selected_pos2 = []
    selected_y = []

    g_rl = tf.Graph()
    sess2 = tf.Session(graph=g_rl)
    env = environment(230)

    with g_rl.as_default():
        with sess2.as_default():

            myAgent = agent(0.02, entity_ebd, 460)
            init = tf.global_variables_initializer()
            sess2.run(init)
            saver = tf.train.Saver()
            saver.restore(sess2, save_path=save_path)
            g_rl.finalize()

            for epoch in range(1):

                total_reward = []
                num_chosen = 0

                all_list = list(range(len(all_sentence_ebd)))

                for batch in tqdm.tqdm(all_list):

                    batch_en1 = train_entitypair[batch][0]
                    batch_en2 = train_entitypair[batch][1]
                    batch_sentence_ebd = all_sentence_ebd[batch]
                    batch_reward = all_reward[batch]
                    batch_len = len(batch_sentence_ebd)

                    batch_word = train_word[batch]
                    batch_pos1 = train_pos1[batch]
                    batch_pos2 = train_pos2[batch]
                    batch_y = [y_train[batch] for x in range(len(batch_word))]

                    # reset environment
                    state = env.reset(batch_en1, batch_en2, batch_sentence_ebd, batch_reward)
                    old_prob = []

                    # get action
                    # start = time.time()
                    for i in range(batch_len):
                        state_in = np.append(state[0], state[1])
                        feed_dict = {}
                        feed_dict[myAgent.entity1] = [state[2]]
                        feed_dict[myAgent.entity2] = [state[3]]
                        feed_dict[myAgent.state_in] = [state_in]
                        prob = sess2.run(myAgent.prob, feed_dict=feed_dict)
                        old_prob.append(prob[0])
                        action = decide_action(prob)
                        # produce data for training cnn model
                        state = env.step(action)
                        if action == 1:
                            num_chosen += 1
                    # print (old_prob)
                    chosen_reward = [batch_reward[x] for x in env.list_selected]
                    total_reward += chosen_reward

                    selected_word += [batch_word[x] for x in env.list_selected]
                    selected_pos1 += [batch_pos1[x] for x in env.list_selected]
                    selected_pos2 += [batch_pos2[x] for x in env.list_selected]
                    selected_y += [batch_y[x] for x in env.list_selected]
                print(num_chosen)
    selected_word = np.array(selected_word)
    selected_pos1 = np.array(selected_pos1)
    selected_pos2 = np.array(selected_pos2)
    selected_y = np.array(selected_y)

    np.save('cnndata/selected_word.npy', selected_word)
    np.save('cnndata/selected_pos1.npy', selected_pos1)
    np.save('cnndata/selected_pos2.npy', selected_pos2)
    np.save('cnndata/selected_y.npy', selected_y)


if __name__ == '__main__':
    print('train rlmodel')
    train()

    # print('select training data')
    # select(save_path='rlmodel/origin_rl_model.ckpt')
    #
    # print('use the selected data to train cnn model')
    # cnnmodel_lstm.train('cnndata/selected_word.npy', 'cnndata/selected_pos1.npy', 'cnndata/selected_pos2.npy','cnndata/selected_y.npy','model/selected_lstm_model.ckpt')
