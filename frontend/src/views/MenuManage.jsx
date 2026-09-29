import Modal from '@c/ui/Modal'
import { ItemTree } from '@/components/items'
import { Plus, Trash2 } from 'lucide-react'

export function MenuManage({ open, onClose }) {
  const handleToggleMenu = (item) => {
    // TODO: add/remove from menu logic
    console.log('toggle menu', item.item_code);
  };

  return (
    <Modal open={open} onClose={onClose} title={__('Menu Management')} size="full">
      <ItemTree
        enabled={open}
        className="flex-1"
        renderActions={(item) => (
          <button
            className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full transition-all ${
              item.in_menu
                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                : 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
            }`}
            onClick={() => handleToggleMenu(item)}
          >
            {item.in_menu ? <Trash2 size={12} /> : <Plus size={12} />}
            {item.in_menu ? __('Remove') : __('Add')}
          </button>
        )}
      />
    </Modal>
  );
}

export default MenuManage;