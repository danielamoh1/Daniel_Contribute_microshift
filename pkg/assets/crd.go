package assets

import (
	"context"
	"fmt"
	"path/filepath"
	"time"

	klog "k8s.io/klog/v2"

	"github.com/openshift/microshift/pkg/config"

	apiextv1 "k8s.io/apiextensions-apiserver/pkg/apis/apiextensions/v1"
	apiextv1beta1 "k8s.io/apiextensions-apiserver/pkg/apis/apiextensions/v1beta1"
	apiext_clientset "k8s.io/apiextensions-apiserver/pkg/client/clientset/clientset"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	apiruntime "k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/serializer"
	"k8s.io/apimachinery/pkg/util/wait"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

const (
	customResourceReadyInterval = 5 * time.Second
	customResourceReadyTimeout  = 10 * time.Minute
)

var (
	apiExtensionsScheme = apiruntime.NewScheme()
	apiExtensionsCodecs = serializer.NewCodecFactory(apiExtensionsScheme)
	crds                = []string{
		"assets/crd/0000_03_security-openshift_01_scc.crd.yaml",
		"assets/crd/0000_03_authorization-openshift_01_rolebindingrestriction.crd.yaml",
	}
)

func isEstablished(cs *apiext_clientset.Clientset, obj apiruntime.Object) (bool, error) {
	var err error
	switch crd := obj.(type) {
	case *apiextv1.CustomResourceDefinition:
		if crd, err = cs.ApiextensionsV1().CustomResourceDefinitions().Get(context.TODO(), crd.Name, metav1.GetOptions{}); err == nil {
			for _, condition := range crd.Status.Conditions {
				if condition.Type == apiextv1.Established && condition.Status == apiextv1.ConditionTrue {
					return true, nil
				}
			}
		}
	case *apiextv1beta1.CustomResourceDefinition:
		if crd, err = cs.ApiextensionsV1beta1().CustomResourceDefinitions().Get(context.TODO(), crd.Name, metav1.GetOptions{}); err == nil {
			for _, condition := range crd.Status.Conditions {
				if condition.Type == apiextv1beta1.Established && condition.Status == apiextv1beta1.ConditionTrue {
					return true, nil
				}
			}
		}
	default:
		panic(fmt.Errorf("unknown type: %T", obj))
	}
	// returns nil error if CRD does not have condition Established == True or a non-nil error
	return false, err
}

func WaitForCrdsEstablished(cfg *config.MicroshiftConfig) error {
	restConfig, err := clientcmd.BuildConfigFromFlags("", filepath.Join(cfg.DataDir, "/resources/kubeadmin/kubeconfig"))
	if err != nil {
		return err
	}

	clientSet := apiext_clientset.NewForConfigOrDie(restConfig)
	for _, crd := range crds {
		klog.Infof("Waiting for crd %s condition.type: established", crd)
		var crdBytes []byte
		crdBytes, err = Asset(crd)
		if err != nil {
			return fmt.Errorf("error getting asset %s: %v", crd, err)
		}
		obj := readCRDOrDie(crdBytes)

		if err = wait.PollImmediate(customResourceReadyInterval, customResourceReadyTimeout, func() (done bool, err error) {
			done, e := isEstablished(clientSet, obj)
			// Intermittent errors can occur when calling the apiserver.  To be on the safe side, log them, but poll until timeout
			if e != nil {
				klog.Errorf("polling for crd condition status \"established\"=\"true\": %v", e)
			}
			return done, nil
		}); err != nil {
			// This will contain only errors generated by wait.PollImmediate (i.e. a timeout error).
			return fmt.Errorf("waiting for default CRD: %v", err)
		}
	}
	return nil
}

func readCRDOrDie(objBytes []byte) apiruntime.Object {
	requiredObj, err := apiruntime.Decode(apiExtensionsCodecs.UniversalDecoder(apiextv1.SchemeGroupVersion, apiextv1beta1.SchemeGroupVersion), objBytes)
	if err != nil {
		panic(err)
	}
	return requiredObj
}

func applyCRD(clientset *apiext_clientset.Clientset, obj apiruntime.Object) error {
	gv := obj.GetObjectKind().GroupVersionKind().GroupVersion()
	switch gv.String() {
	case "apiextensions.k8s.io/v1":
		v1Obj := obj.(*apiextv1.CustomResourceDefinition)
		_, err := clientset.ApiextensionsV1().CustomResourceDefinitions().Get(context.TODO(), v1Obj.Name, metav1.GetOptions{})
		if apierrors.IsNotFound(err) {
			_, err := clientset.ApiextensionsV1().CustomResourceDefinitions().Create(context.TODO(), v1Obj, metav1.CreateOptions{})
			return err
		}
	case "apiextensions.k8s.io/v1beta1":
		v1beta1Obj := obj.(*apiextv1beta1.CustomResourceDefinition)
		_, err := clientset.ApiextensionsV1beta1().CustomResourceDefinitions().Get(context.TODO(), v1beta1Obj.Name, metav1.GetOptions{})
		if apierrors.IsNotFound(err) {
			_, err := clientset.ApiextensionsV1beta1().CustomResourceDefinitions().Create(context.TODO(), v1beta1Obj, metav1.CreateOptions{})
			return err
		}
	default:
		// panic("unknown type %s", t)
	}
	return nil
}

func init() {
	if err := apiextv1.AddToScheme(apiExtensionsScheme); err != nil {
		panic(err)
	}
	if err := apiextv1beta1.AddToScheme(apiExtensionsScheme); err != nil {
		panic(err)
	}
}

func ApplyCRDs(cfg *config.MicroshiftConfig) error {
	lock.Lock()
	defer lock.Unlock()

	restConfig, err := clientcmd.BuildConfigFromFlags("", filepath.Join(cfg.DataDir, "/resources/kubeadmin/kubeconfig"))
	if err != nil {
		return err
	}

	apiExtClientSet := apiext_clientset.NewForConfigOrDie(rest.AddUserAgent(restConfig, "crd-agent"))

	for _, crd := range crds {
		klog.Infof("Applying openshift CRD %s", crd)
		crdBytes, err := Asset(crd)
		if err != nil {
			return fmt.Errorf("error getting asset %s: %v", crd, err)
		}
		c := readCRDOrDie(crdBytes)
		if err := wait.Poll(customResourceReadyInterval, customResourceReadyTimeout, func() (bool, error) {
			if err := applyCRD(apiExtClientSet, c); err != nil {
				klog.Warningf("failed to apply openshift CRD %s: %v", crd, err)
				return false, nil
			}
			klog.Infof("Applied openshift CRD %s", crd)
			return true, nil
		}); err != nil {
			if err == wait.ErrWaitTimeout {
				return fmt.Errorf("%v during syncCustomResourceDefinitions", err)
			}
			return err
		}
	}

	return nil
}
