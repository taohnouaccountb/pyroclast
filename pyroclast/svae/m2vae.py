import sonnet as snt
import tensorflow as tf
import tensorflow_probability as tfp


class M2VAE(snt.AbstractModule):
    """M2 VAE model from Kinga et al. 2014 'Semi-supervised Learning with Deep
    Generative Models'
    """

    def __init__(self,
                 classifier,
                 encoder,
                 decoder,
                 prior,
                 posterior,
                 output_dist,
                 num_classes,
                 name='m2_vae'):
        """
        Args:
            classifier (Tensor -> Tensor): Called $q_\phi(y|x)$, takes data and
                gives class logits
            encoder (Tensor -> Tensor -> (Tensor, Tensor)): Called
                $q_\phi(z|x,y)$, takes data and class label and outputs loc and
                scale values
            decoder (Tensor -> Tensor): Called $p_\theta(x|y,z)$, takes
                class label and latent vector and outputs data reconstruction
            prior (tfp.Distribution): distribution with sample shape equal to latent shape
            posterior (Tensor -> Tensor -> tfp.Distribution): Callable which
                takes location and scale and returns a tfp distribution
            output_dist (Tensor -> tfp.Distribution): Callable from loc to a
                tfp distribution
            num_classes (int): number of classes in the classification problem
        """
        super(M2VAE, self).__init__(name=name)
        self._classifier = classifier
        self._encoder = encoder
        self._decoder = decoder
        self._prior = prior
        self._posterior = posterior
        self._output_dist = output_dist
        self._num_classes = num_classes

    def _build(self, inputs):
        """
        Args:
            inputs (Tensor): input data

        Returns:
            (tfp.Distribution, tfp.Distribution, tfp.Distribution, Tensor): output
                distribution `p_x`, classification `p_y`, and latent posterior
                `p_z`
        """
        x = inputs

        # calculate $q_\phi(y|x)$ and sample `y_hat`
        class_logits = self._classifier(x)
        p_y = tfp.distributions.ExpRelaxedOneHotCategorical(
            logits=class_logits, temperature=0.5)
        y_hat = p_y.sample()

        # calculate $q_\phi(z|x,y)$ and sample `z`
        loc, scale = self._encoder(x, y_hat)
        p_z = self._posterior(loc, scale)
        z = p_z.sample()

        # calculate $p_\theta(x|y,z)$
        output_loc = self._decoder(y_hat, z)
        p_x = tfp.distributions.Independent(
            self._output_dist(output_loc), reinterpreted_batch_ndims=3)

        return p_x, p_y, p_z, z

    def supervised_loss(self, x, y):
        """Calculate $-\mathcal{L}(x,y)$

        Args:
            x (Tensor): data
            y (Tensor): one hot vector labels

        Returns:
            Tensor: scalar loss value
        """
        p_x, p_y, p_z, z = self._build(x)
        logpx = p_x.log_prob(x)
        logpy = p_y.log_prob(y)
        logpz = self._prior.log_prob(z)
        logqz = p_z.log_prob(z)
        # reduce_sum on pz - qz here or above, not sure
        return logpx + tf.reduce_sum(
            logpy, axis=0) + tf.reduce_sum(
                logpz - logqz, axis=-1)

    def unsupervised_loss(self, x):
        """Calculate $-\mathcal{U}{x}

        Args:
            x (Tensor): data

        Returns:
            Tensor: scalar loss value
        """
        _, p_y, _, _ = self._build(x)
        y_values = range(self._num_classes)
        y_losses = []
        for y in y_values:
            supervised_component = self.supervised_loss(
                x, tf.one_hot(y, self._num_classes))
            logqy = p_y.log_prob(y)
            y_losses.append(supervised_component + logqy)
        return sum(y_losses) + tfp.distributions.Categorical(
            p_y.logits).entropy()

    def loss(self, x_label, y_label, x_unlabel):
        """J^alpha from Kingma et al. 2014
        """
        unsupervised_loss = self.unsupervised_loss(x_unlabel)
        supervised_loss = self.supervised_loss(x_label, y_label)
        _, p_y, _, _ = self._build(x_label)
        return unsupervised_loss + supervised_loss + p_y.log_prob(y_label)
