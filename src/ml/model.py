import random
from collections import defaultdict
from typing import Dict, List, Tuple, Union

import tensorflow as tf
from tensorflow.keras.layers import Dense
from tensorflow.keras.models import Model

"""
Below is what was used for training the most recent version of the model:

Optimizer: Adagrad, with default hyperparameters

Loss: Binary Crossentropy + MSE(adj_mtx,decoded_for_reg)
    - adj_mtx is the adjacency matrix created by create_mtx.py
    and then updated such that each row sums to 1.
    - decoded_for_reg is an output of the model

Epochs: 100

Batch Size: 64
"""
EMBED_SIZE = 64
VOCAB_SIZE = 8
PATH_COUNT = 32
RNN_SIZE = 32


class Encoder(Model):
    """
    Encoder part of the model -> compress dimensionality
    """
    def __init__(self, name, cards, max_cube_size, batch_size):
        super().__init__()
        self.assigned_name = name
        self.max_cube_size = max_cube_size
        self.batch_size = batch_size
        self.flatten = tf.keras.layers.Flatten(name=name + "_flatten")
        self.__preprocess_cards(cards)
        # self.input_drop = Dropout(0.2)
        self.encoded_1 = Dense(512, activation='relu', name=name + "_e1")
        # self.e1_drop = Dropout(0.5)
        self.encoded_2 = Dense(256, activation='relu', name=name + "_e2")
        # self.e2_drop = Dropout(0.5)
        self.encoded_3 = Dense(128, activation='relu', name=name + "_e3")
        # self.e3_drop = Dropout(0.2)
        self.bottleneck = Dense(64, activation='relu',
                                name=name + "_bottleneck")

    def __preprocess_cards(self, cards):
        self.card_tensors = tf.keras.layers.Embedding(len(cards) + 1, EMBED_SIZE)
        return
        def convert_structure(structure: Union[list, dict, int, str, bool],
                              key: str, vocab_dict: Dict[str, int],
                              children: List[List[int]],
                              node_labels: List[int],
                              node_heights: List[int],
                              node_depths: List[int],
                              depth: int) -> Tuple[int, int]:
            our_children = []
            max_child_height = 0
            if isinstance(structure, list):
                for index, child in enumerate(structure):
                    child_index, height = convert_structure(child, str(index),
                                                            vocab_dict, children,
                                                            node_labels, node_heights,
                                                            node_depths, depth + 1)
                    our_children.append(child_index)
                    max_child_height = max(max_child_height, height)
            elif isinstance(structure, dict):
                for key, child in structure.items():
                    child_index, height = convert_structure(child, key, vocab_dict,
                                                            children, node_labels, node_heights,
                                                            node_depths, depth + 1)
                    our_children.append(child_index)
                    max_child_height = max(max_child_height, height)
            else:
                key = f'{key}.{structure}'
                if key in vocab_dict:
                    vocab = vocab_dict[key]
                else:
                    vocab = len(vocab_dict)
                    vocab_dict[key] = vocab
                our_index = len(node_labels)
                node_labels.append(vocab)
                node_heights.append(0)
                for index in range(len(children)):
                    children[index].append(0)
                node_depths.append(depth)
                return our_index, 0
            if key in vocab_dict:
                vocab = vocab_dict[key]
            else:
                vocab = len(vocab_dict)
                vocab_dict[key] = vocab
            for _ in range(len(structure), len(children)):
                our_children.append(-1)
            our_index = len(node_labels)
            for index, child_index in enumerate(our_children):
                if len(children) <= index:
                    children.append([0 for _ in node_labels])
                children[index].append(0)
            node_labels.append(vocab)
            node_heights.append(max_child_height + 1)
            node_depths.append(depth)
            return our_index, max_child_height + 1

        vocab_dict = {"": 0}
        children = []
        node_labels = [0]
        card_indices = []
        node_heights = [-1]
        node_depths = [-1]
        for card in cards:
            card_index, _ = convert_structure(card, "", vocab_dict, children,
                                              node_labels, node_heights, node_depths, 0)
            card_indices.append(card_index)
        children_count = len(children)
        node_count = len(node_labels)
        print(len(vocab_dict), node_count, children_count)
        children = [[child[i] for child in children]
                    for i in range(node_count)]
        node_parents = [0 for _ in range(node_count)]
        for i, our_children in enumerate(children):
            for child in our_children:
                if child != 0:
                    node_parents[child] = i
        all_paths = [[]]
        max_path_length = 0
        max_paths = 0
        for i, max_index in enumerate(card_indices):
            if i == 0:
                continue
            min_index = card_indices[i - 1] + 1
            paths = []
            index_range = [x for x in range(min_index, max_index) if node_heights[x] == 0]
            computed_values = defaultdict(lambda: defaultdict(lambda: False))
            iterations = 0
            if len(index_range) == 0:
                all_paths.append([])
                continue
            while len(paths) < PATH_COUNT and iterations < PATH_COUNT * 1.2:
                iterations += 1
                start = random.choice(index_range)
                remaining = [x for x in index_range if x != start and not computed_values[start][x]]
                if len(remaining) == 0:
                    continue
                end = random.choice(remaining)
                computed_values[start][end] = True
                computed_values[end][start] = True
                start_depth = node_depths[start]
                end_depth = node_depths[end]
                if end_depth > start_depth:
                    start, end = end, start
                    start_depth, end_depth = end_depth, start_depth
                path = [node_labels[start]]
                end_path = [node_labels[end]]
                while start_depth > end_depth:
                    start = node_parents[start]
                    start_depth -= 1
                    path.append(start)
                while node_parents[start] != node_parents[end]:
                    start = node_parents[start]
                    end = node_parents[end]
                    path.append(start)
                    end_path.append(end)
                path.append(node_parents[start])
                path += end_path[::-1]
                paths.append(path)
                max_path_length = max(len(path), max_path_length)
            all_paths.append(paths)
            max_paths = max(len(paths), max_paths)
        path_lengths = []
        for node_paths in all_paths:
            our_path_lengths = []
            for path in node_paths:
                our_path_lengths.append(len(path))
                for _ in range(len(path), max_path_length):
                    path.append(0)
            for _ in range(len(node_paths), max_paths):
                node_paths.append([0 for _ in range(max_path_length)])
                our_path_lengths.append(0)
            path_lengths.append(our_path_lengths)

        all_paths = tf.constant(all_paths)
        path_lengths = tf.constant(path_lengths)
        print(tf.shape(all_paths), tf.shape(path_lengths))
        self.embedding = tf.keras.layers.Embedding(len(vocab_dict), VOCAB_SIZE,
                                                   name=self.assigned_name + "_vocab_embedding")
        rnn_cell_fw = tf.keras.layers.LSTMCell(RNN_SIZE // 2)
        rnn_cell_bw = tf.keras.layers.LSTMCell(RNN_SIZE // 2)
        self.rnn = tf.keras.layers.Bidirectional(
            layer=tf.keras.layers.RNN(rnn_cell_fw, return_state=True),
            backward_layer=tf.keras.layers.RNN(rnn_cell_bw, go_backwards=True,
                                               return_state=True),
            merge_mode="concat",
            name=self.assigned_name + "_bidirectional",
            dtype=tf.float32)
        # rnn_cell = tf.keras.layers.LSTMCell(RNN_SIZE)
        # self.rnn = tf.keras.layers.RNN(rnn_cell, dtype=tf.float32, return_state=True)
        self.embed_dense_layer = tf.keras.layers.Dense(units=EMBED_SIZE,
                                                       activation=tf.nn.tanh, use_bias=False)

        all_path_embed = self.embedding(all_paths, training=True)
        flat_paths = tf.reshape(all_path_embed, shape=[-1, max_path_length, VOCAB_SIZE])
        flat_valid_contexts_mask = tf.expand_dims(tf.sequence_mask(tf.reshape(path_lengths, [-1]),
                                                                   maxlen=max_path_length,
                                                                   dtype=tf.float32), axis=-1)
        _, state_fw, _, state_bw, _ = self.rnn(inputs=flat_paths, mask=flat_valid_contexts_mask,
                                               training=True)
        final_rnn_state = tf.concat([state_fw, state_bw], -1)

        # _, final_rnn_state, _ = self.rnn(inputs=flat_paths, mask=flat_valid_contexts_mask,
        #                                  training=True)
        path_nodes_aggregation = tf.reshape(final_rnn_state, [-1, max_paths * RNN_SIZE])
        self.card_tensors = self.embed_dense_layer(inputs=path_nodes_aggregation)
        print(tf.shape(self.card_tensors))
        self.num_cards = len(cards)
        print("finished preprocessing cards.")
        
    def call(self, x, **kwargs):
        print("called encoder.")
        # x = self.card_tensors(x)
        # x = tf.nn.embedding_lookup(self.card_tensors, x)
        print(x.shape)
        # x = self.flatten(x)
        print(x.shape)
        encoded = self.encoded_1(x)
        # encoded = self.e1_drop(encoded)
        encoded = self.encoded_2(encoded)
        # encoded = self.e2_drop(encoded)
        encoded = self.encoded_3(encoded)
        # encoded = self.e3_drop(encoded)
        return self.bottleneck(encoded)

    # def call_for_reg(self, x):
    #     encoded = self.encoded_1(x)
    #     encoded = self.encoded_2(encoded)
    #     encoded = self.encoded_3(encoded)
    #     return self.bottleneck(encoded)


class Decoder(Model):
    """
    Decoder part of the model -> expand from compressed latent
        space back to the input space
    """
    def __init__(self, name, output_dim, output_act):
        super().__init__()
        # self.bottleneck_drop = Dropout(0.2)
        self.decoded_1 = Dense(128, activation='relu', name=name + "_d1")
        # self.d1_drop = Dropout(0.4)
        self.decoded_2 = Dense(256, activation='relu', name=name + "_d2")
        # self.d2_drop = Dropout(0.4)
        self.decoded_3 = Dense(512, activation='relu', name=name + "_d3")
        # self.d3_drop = Dropout(0.2)
        self.reconstruct = Dense(output_dim, activation=output_act,
                                 name=name + "_reconstruction")

    def call(self, x, **kwargs):
        decoded = self.decoded_1(x)
        decoded = self.decoded_2(decoded)
        decoded = self.decoded_3(decoded)
        return self.reconstruct(decoded)

    # def call_for_reg(self, x):
    #     x = self.bottleneck_drop(x)
    #     decoded = self.decoded_1(x)
    #     decoded = self.d1_drop(decoded)
    #     decoded = self.decoded_2(decoded)
    #     decoded = self.d2_drop(decoded)
    #     decoded = self.decoded_3(decoded)
    #     decoded = self.d3_drop(decoded)
    #     return self.reconstruct(decoded)


class CC_Recommender(Model):
    """
    AutoEncoder build as a recommender system based on the following idea:

        If our input is a binary vector where 1 represents the presence of an
        item in a collection, then an autoencoder trained
    """
    def __init__(self, cards, max_cube_size, batch_size):
        super().__init__()
        self.N = len(cards)
        self.encoder = Encoder("encoder", cards, max_cube_size, batch_size)
        # sigmoid because input is a binary vector we want to reproduce
        self.decoder = Decoder("main", self.N, output_act='sigmoid')
        # softmax because the graph information is probabilities
        # self.input_noise = Dropout(0.5)
        # self.latent_noise = Dropout(0.2)
        self.decoder_for_reg = Decoder("reg", self.N, output_act='softmax')

    def call(self, input, **kwargs):
        """
        input contains two things:
            input[0] = the binary vectors representing the collections
            input[1] = a diagonal matrix of size (self.N X self.N)

        We run the same encoder for each type of input, but with different
        decoders. This is because the goal is to make sure that the compression
        for collections still does a reasonable job compressing individual
        items. So a penalty term (regularization) is added to the model in the
        ability to reconstruct the probability distribution (adjacency matrix)
        on the item level from the encoding.

        The hope is that this regularization enforces this conditional
        probability to be embedded in the recommendations. As the individual
        items must pull towards items represented strongly within the graph.
        """
        x, identity = input
        # x = self.input_noise(x)
        encoded = self.encoder(x)
        # latent_for_reconstruct = self.latent_noise(encoded)
        reconstruction = self.decoder(encoded)
        encode_for_reg = self.encoder(identity)
        # latent_for_reg = self.latent_noise(encode_for_reg)
        decoded_for_reg = self.decoder_for_reg(encode_for_reg)
        return reconstruction, decoded_for_reg
