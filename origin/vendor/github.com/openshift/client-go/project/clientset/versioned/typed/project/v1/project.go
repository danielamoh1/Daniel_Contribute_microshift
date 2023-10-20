// Code generated by client-gen. DO NOT EDIT.

package v1

import (
	"context"
	json "encoding/json"
	"fmt"
	"time"

	v1 "github.com/openshift/api/project/v1"
	projectv1 "github.com/openshift/client-go/project/applyconfigurations/project/v1"
	scheme "github.com/openshift/client-go/project/clientset/versioned/scheme"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	types "k8s.io/apimachinery/pkg/types"
	watch "k8s.io/apimachinery/pkg/watch"
	rest "k8s.io/client-go/rest"
)

// ProjectsGetter has a method to return a ProjectInterface.
// A group's client should implement this interface.
type ProjectsGetter interface {
	Projects() ProjectInterface
}

// ProjectInterface has methods to work with Project resources.
type ProjectInterface interface {
	Create(ctx context.Context, project *v1.Project, opts metav1.CreateOptions) (*v1.Project, error)
	Update(ctx context.Context, project *v1.Project, opts metav1.UpdateOptions) (*v1.Project, error)
	UpdateStatus(ctx context.Context, project *v1.Project, opts metav1.UpdateOptions) (*v1.Project, error)
	Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error
	DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error
	Get(ctx context.Context, name string, opts metav1.GetOptions) (*v1.Project, error)
	List(ctx context.Context, opts metav1.ListOptions) (*v1.ProjectList, error)
	Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error)
	Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *v1.Project, err error)
	Apply(ctx context.Context, project *projectv1.ProjectApplyConfiguration, opts metav1.ApplyOptions) (result *v1.Project, err error)
	ApplyStatus(ctx context.Context, project *projectv1.ProjectApplyConfiguration, opts metav1.ApplyOptions) (result *v1.Project, err error)
	ProjectExpansion
}

// projects implements ProjectInterface
type projects struct {
	client rest.Interface
}

// newProjects returns a Projects
func newProjects(c *ProjectV1Client) *projects {
	return &projects{
		client: c.RESTClient(),
	}
}

// Get takes name of the project, and returns the corresponding project object, and an error if there is any.
func (c *projects) Get(ctx context.Context, name string, options metav1.GetOptions) (result *v1.Project, err error) {
	result = &v1.Project{}
	err = c.client.Get().
		Resource("projects").
		Name(name).
		VersionedParams(&options, scheme.ParameterCodec).
		Do(ctx).
		Into(result)
	return
}

// List takes label and field selectors, and returns the list of Projects that match those selectors.
func (c *projects) List(ctx context.Context, opts metav1.ListOptions) (result *v1.ProjectList, err error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	result = &v1.ProjectList{}
	err = c.client.Get().
		Resource("projects").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Do(ctx).
		Into(result)
	return
}

// Watch returns a watch.Interface that watches the requested projects.
func (c *projects) Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	opts.Watch = true
	return c.client.Get().
		Resource("projects").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Watch(ctx)
}

// Create takes the representation of a project and creates it.  Returns the server's representation of the project, and an error, if there is any.
func (c *projects) Create(ctx context.Context, project *v1.Project, opts metav1.CreateOptions) (result *v1.Project, err error) {
	result = &v1.Project{}
	err = c.client.Post().
		Resource("projects").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(project).
		Do(ctx).
		Into(result)
	return
}

// Update takes the representation of a project and updates it. Returns the server's representation of the project, and an error, if there is any.
func (c *projects) Update(ctx context.Context, project *v1.Project, opts metav1.UpdateOptions) (result *v1.Project, err error) {
	result = &v1.Project{}
	err = c.client.Put().
		Resource("projects").
		Name(project.Name).
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(project).
		Do(ctx).
		Into(result)
	return
}

// UpdateStatus was generated because the type contains a Status member.
// Add a +genclient:noStatus comment above the type to avoid generating UpdateStatus().
func (c *projects) UpdateStatus(ctx context.Context, project *v1.Project, opts metav1.UpdateOptions) (result *v1.Project, err error) {
	result = &v1.Project{}
	err = c.client.Put().
		Resource("projects").
		Name(project.Name).
		SubResource("status").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(project).
		Do(ctx).
		Into(result)
	return
}

// Delete takes name of the project and deletes it. Returns an error if one occurs.
func (c *projects) Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error {
	return c.client.Delete().
		Resource("projects").
		Name(name).
		Body(&opts).
		Do(ctx).
		Error()
}

// DeleteCollection deletes a collection of objects.
func (c *projects) DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error {
	var timeout time.Duration
	if listOpts.TimeoutSeconds != nil {
		timeout = time.Duration(*listOpts.TimeoutSeconds) * time.Second
	}
	return c.client.Delete().
		Resource("projects").
		VersionedParams(&listOpts, scheme.ParameterCodec).
		Timeout(timeout).
		Body(&opts).
		Do(ctx).
		Error()
}

// Patch applies the patch and returns the patched project.
func (c *projects) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *v1.Project, err error) {
	result = &v1.Project{}
	err = c.client.Patch(pt).
		Resource("projects").
		Name(name).
		SubResource(subresources...).
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(data).
		Do(ctx).
		Into(result)
	return
}

// Apply takes the given apply declarative configuration, applies it and returns the applied project.
func (c *projects) Apply(ctx context.Context, project *projectv1.ProjectApplyConfiguration, opts metav1.ApplyOptions) (result *v1.Project, err error) {
	if project == nil {
		return nil, fmt.Errorf("project provided to Apply must not be nil")
	}
	patchOpts := opts.ToPatchOptions()
	data, err := json.Marshal(project)
	if err != nil {
		return nil, err
	}
	name := project.Name
	if name == nil {
		return nil, fmt.Errorf("project.Name must be provided to Apply")
	}
	result = &v1.Project{}
	err = c.client.Patch(types.ApplyPatchType).
		Resource("projects").
		Name(*name).
		VersionedParams(&patchOpts, scheme.ParameterCodec).
		Body(data).
		Do(ctx).
		Into(result)
	return
}

// ApplyStatus was generated because the type contains a Status member.
// Add a +genclient:noStatus comment above the type to avoid generating ApplyStatus().
func (c *projects) ApplyStatus(ctx context.Context, project *projectv1.ProjectApplyConfiguration, opts metav1.ApplyOptions) (result *v1.Project, err error) {
	if project == nil {
		return nil, fmt.Errorf("project provided to Apply must not be nil")
	}
	patchOpts := opts.ToPatchOptions()
	data, err := json.Marshal(project)
	if err != nil {
		return nil, err
	}

	name := project.Name
	if name == nil {
		return nil, fmt.Errorf("project.Name must be provided to Apply")
	}

	result = &v1.Project{}
	err = c.client.Patch(types.ApplyPatchType).
		Resource("projects").
		Name(*name).
		SubResource("status").
		VersionedParams(&patchOpts, scheme.ParameterCodec).
		Body(data).
		Do(ctx).
		Into(result)
	return
}