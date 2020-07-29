# Copyright (c) 2018 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import numpy as np

import paddle.fluid as fluid
from paddle.fluid.dygraph import to_variable
from paddle.fluid.framework import ParamBase


class L1(fluid.Layer):
    def __init__(self):
        super(L1, self).__init__()
        self._param_attr = fluid.ParamAttr(
            initializer=fluid.initializer.Constant(value=0.1))
        self.w1 = self.create_parameter(
            attr=self._param_attr, shape=[2, 2], dtype='float32', is_bias=False)
        self.w2 = self.create_parameter(
            attr=self._param_attr, shape=[2, 2], dtype='float32', is_bias=False)

    def forward(self):
        return self.w1 + self.w2


class L2(fluid.Layer):
    def __init__(self):
        super(L2, self).__init__()
        self.layer1 = L1()
        self.layer2 = L1()

    def forward(self):
        return self.layer1() + self.layer2()


class L3(fluid.Layer):
    def __init__(self):
        super(L3, self).__init__()
        self.layer1 = L2()
        self.layer2 = L2()

    def forward(self):
        return self.layer1() + self.layer2()


class TestBaseLayer(unittest.TestCase):
    def test_one_level(self):
        with fluid.dygraph.guard():
            l = L1()
            ret = l()
            expected_names = ['l1.w1', 'l1.w2']
            idx = 0
            for name, _ in l.named_parameters(prefix='l1'):
                self.assertEqual(name, expected_names[idx])
                idx += 1
            self.assertTrue(np.allclose(ret.numpy(), 0.2 * np.ones([2, 2])))

    def test_three_level(self):
        with fluid.dygraph.guard():
            l = L3()
            expected_names = [
                'l3.layer1.layer1.w1',
                'l3.layer1.layer1.w2',
                'l3.layer1.layer2.w1',
                'l3.layer1.layer2.w2',
                'l3.layer2.layer1.w1',
                'l3.layer2.layer1.w2',
                'l3.layer2.layer2.w1',
                'l3.layer2.layer2.w2',
            ]
            idx = 0
            for name, _ in l.named_parameters(prefix='l3'):
                self.assertEqual(name, expected_names[idx])
                idx += 1
            ret = l()
            self.assertTrue(np.allclose(ret.numpy(), 0.8 * np.ones([2, 2])))


class BufferLayer(fluid.Layer):
    def __init__(self):
        super(BufferLayer, self).__init__()
        buffer_var = to_variable(np.zeros([2, 4]).astype('int32'))
        self.register_buffer("layer_buffer", buffer_var)

    def forward(self):
        pass


class BufferNet(fluid.Layer):
    def __init__(self):
        super(BufferNet, self).__init__()
        self.buffer_layer = BufferLayer()
        self.w1 = self.create_parameter(
            shape=[2, 2], dtype='float32', is_bias=False)
        buffer_var = to_variable(np.ones([2, 4]).astype('int32'))
        self.register_buffer("net_buffer", buffer_var)

        self.new_buffer = to_variable(np.ones([4, 2]).astype('int32'))

    def forward(self):
        pass


class TestBuffer(unittest.TestCase):
    def test_buffers_and_named_buffers(self):
        def names(named_buffers):
            return [name for name, _ in named_buffers]

        with fluid.dygraph.guard():
            layer = BufferLayer()
            net = BufferNet()

            self.assertEqual(len(layer.buffers()), 1)
            self.assertEqual(names(layer.named_buffers()), ['layer_buffer'])

            self.assertEqual(len(net.buffers()), 3)
            self.assertEqual(
                names(net.named_buffers()),
                ['net_buffer', 'new_buffer', 'buffer_layer.layer_buffer'])

            self.assertEqual(len(net.buffers(include_sublayers=False)), 2)
            self.assertEqual(
                names(net.named_buffers(include_sublayers=False)),
                ['net_buffer', 'new_buffer'])

    def test_register_buffer_with_error(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var = to_variable(np.zeros([1]))

            with self.assertRaisesRegexp(TypeError,
                                         "name of buffer should be a string"):
                net.register_buffer(12, var)

            with self.assertRaisesRegexp(TypeError,
                                         "buffer should be a core.VarBase"):
                net.register_buffer("buffer_name", ParamBase([2, 2], 'float32'))

            with self.assertRaisesRegexp(KeyError,
                                         "name of buffer can not contain"):
                net.register_buffer("buffer.name", var)

            with self.assertRaisesRegexp(KeyError,
                                         "name of buffer can not be empty"):
                net.register_buffer("", var)

            net.attr_name = 10
            with self.assertRaisesRegexp(KeyError, "already exists"):
                net.register_buffer("attr_name", var)

            del net.attr_name
            net.attr_name = ParamBase([2, 2], 'float32')
            with self.assertRaisesRegexp(KeyError, "already exists"):
                net.register_buffer("attr_name", var)

    def test_register_buffer_same_name(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))
            var2 = to_variable(np.zeros([2]))
            var3 = to_variable(np.zeros([3]))

            net.register_buffer("buffer_name", var1)
            self.assert_var_base_equal(net.buffer_name, var1)
            net.register_buffer("buffer_name", var2)
            self.assert_var_base_equal(net.buffer_name, var2)
            net.register_buffer("buffer_name", var3)
            self.assert_var_base_equal(net.buffer_name, var3)

    def test_buffer_not_persistable(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))

            net.register_buffer("buffer_name", var1, persistable=False)
            self.assertEqual(len(net.buffers()), 1)
            self.assertEqual(len(net.state_dict()), 0)

    def test_buffer_not_persistable_del(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))
            net.register_buffer("buffer_name", var1, persistable=False)
            del net.buffer_name
            self.assertEqual(len(net.buffers()), 0)

    def test_buffer_not_persistable_overwrite(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))
            var2 = to_variable(np.zeros([2]))
            net.register_buffer("buffer_name", var1, persistable=False)
            net.register_buffer("buffer_name", var2)

            # Allow to overwrite a non-persistable buffer with a persistable var.
            self.assertEqual(len(net.buffers()), 1)
            self.assertEqual(len(net.state_dict()), 1)

            net.register_buffer("buffer_name", var1, persistable=False)
            self.assertEqual(len(net.buffers()), 1)
            self.assertEqual(len(net.state_dict()), 0)

    def test_buffer_not_persistable_assign(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))
            net.register_buffer("buffer_name", var1, persistable=False)

            # Assigning Nones will remove the buffer, but allow to re-assign
            # to remark it as buffer.
            net.buffer_name = None
            self.assertEqual(len(net.buffers()), 0)
            self.assertEqual(len(net.state_dict()), 0)

            net.buffer_name = var1
            self.assertEqual(len(net.buffers()), 1)
            self.assertEqual(len(net.state_dict()), 0)

            # Re-assign a ParamBase will remove the buffer.
            net.buffer_name = ParamBase([2, 2], 'float32')
            self.assertEqual(len(net.buffers()), 0)
            self.assertEqual(len(net.state_dict()), 1)

    def test_buffer_not_persistable_load(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([1]))
            net.register_buffer("buffer_name", var1, persistable=False)
            net.load_dict({})

    def test_buffer_state_dict(self):
        with fluid.dygraph.guard():
            net = fluid.Layer()
            var1 = to_variable(np.zeros([2, 3]))
            var2 = to_variable(np.zeros([3, 2]))
            net.register_buffer("buffer_var1", var1)
            net.register_buffer("buffer_var2", var2, persistable=False)

            self.assertEqual(len(net.state_dict()), 1)
            self.assertEqual([name for name, _ in net.state_dict().items()],
                             ["buffer_var1"])

            # load state_dict
            net_load = fluid.Layer()
            var = to_variable(np.ones([2, 3]))
            net_load.register_buffer("buffer_var1", var)
            net_load.load_dict(net.state_dict())

            self.assert_var_base_equal(net_load.buffer_var1, var1)

    def assert_var_base_equal(self, var1, var2):
        self.assertTrue(np.array_equal(var1.numpy(), var2.numpy()))


if __name__ == '__main__':
    unittest.main()