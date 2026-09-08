#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <wayland-client.h>
#include "pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
 if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name)) manager=wl_registry_bind(registry,name,&zwlr_virtual_pointer_manager_v1_interface,1);
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
int main(void) {
 struct wl_display *display=wl_display_connect(NULL);
 if(!display) return 1;
 struct wl_registry *registry=wl_display_get_registry(display);
 const struct wl_registry_listener listener={global,removed};
 wl_registry_add_listener(registry,&listener,NULL);
 wl_display_roundtrip(display);
 if(!manager) return 2;
 struct zwlr_virtual_pointer_v1 *pointer=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager,NULL);
 wl_display_roundtrip(display);
 puts("ready"); fflush(stdout);
 char command[64]; unsigned a,b;
 while(fgets(command,sizeof command,stdin)) {
  if(sscanf(command,"move %u %u",&a,&b)==2) zwlr_virtual_pointer_v1_motion_absolute(pointer,1,a,b,800,600);
  else if(sscanf(command,"press %u",&a)==1) zwlr_virtual_pointer_v1_button(pointer,1,a,1);
  else if(sscanf(command,"release %u",&a)==1) zwlr_virtual_pointer_v1_button(pointer,1,a,0);
  else if(!strncmp(command,"scroll ",7)) {
   int direction = !strncmp(command+7,"up",2) ? -1 : 1;
   zwlr_virtual_pointer_v1_axis_source(pointer,WL_POINTER_AXIS_SOURCE_WHEEL);
   zwlr_virtual_pointer_v1_axis_discrete(pointer,1,WL_POINTER_AXIS_VERTICAL_SCROLL,wl_fixed_from_int(direction*10),direction);
  }
  zwlr_virtual_pointer_v1_frame(pointer);
  wl_display_roundtrip(display);
  puts("ok"); fflush(stdout);
 }
 zwlr_virtual_pointer_v1_destroy(pointer); wl_display_roundtrip(display); wl_display_disconnect(display); return 0;
}
