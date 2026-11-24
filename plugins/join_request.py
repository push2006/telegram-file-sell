# Modifications copyright push2006. Original notices and LICENSE retained.
from hydrogram import Client
from hydrogram.types import ChatJoinRequest, ChatMemberUpdated
from hydrogram.enums import ChatMemberStatus

@Client.on_chat_join_request()
async def handle_join_request(client, join_request: ChatJoinRequest):
    """Handle join request for fsub channels"""
    user_id = join_request.from_user.id
    channel_id = join_request.chat.id
    
    # Marketplace personal invite links are distinct from legacy force-sub links.
    from datetime import datetime
    url=getattr(getattr(join_request,"invite_link",None),"invite_link",None)
    if url:
        invite=await client.mongodb.db.business_invites.find_one({"_id":url})
        if invite:
            allowed=(invite["user_id"]==user_id and invite["channel_id"]==channel_id and invite["expires_at"]>datetime.now() and not await client.mongodb.is_banned(user_id) and await client.mongodb.has_category_access(user_id,invite["category_id"]))
            if allowed:
                await client.approve_chat_join_request(channel_id,user_id)
                try: await client.revoke_chat_invite_link(channel_id,url)
                except Exception: pass
                await client.mongodb.db.business_invites.update_one({"_id":url},{"$set":{"used":True,"expires_at":datetime.now()}})
            else:
                await client.decline_chat_join_request(channel_id,user_id)
            return
    if channel_id not in client.fsub_dict:
        return
        
    # Check if user is banned
    if await client.mongodb.is_banned(user_id):
        return
    
    try:
        # Ensure user exists in database
        if not await client.mongodb.present_user(user_id):
            await client.mongodb.add_user(user_id)
        
        # Record join request
        await client.mongodb.add_join_request(user_id, channel_id, getattr(join_request, 'id', None))
        await client.mongodb.update_fsub_status(user_id, channel_id, "request_submitted")
        await client.mongodb.add_channel_user(channel_id, user_id)
        
    except Exception as e:
        client.LOGGER(__name__, client.name).error(f"Join request error: {user_id} in {channel_id}: {e}")

@Client.on_chat_member_updated()
async def handle_member_update(client, chat_member_updated: ChatMemberUpdated):
    """Handle member status updates for fsub channels"""
    user_id = chat_member_updated.from_user.id
    channel_id = chat_member_updated.chat.id
    
    # Only process monitored fsub channels
    if channel_id not in client.fsub_dict:
        return
    
    old_status = chat_member_updated.old_chat_member.status if chat_member_updated.old_chat_member else None
    new_status = chat_member_updated.new_chat_member.status if chat_member_updated.new_chat_member else None
    
    try:
        # Ensure user exists
        if not await client.mongodb.present_user(user_id):
            await client.mongodb.add_user(user_id)
        
        # Handle status changes properly - Telegram sends None for new_status on leave/ban
        active_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
        
        # User joined - old_status is None/inactive, new_status is active
        if new_status in active_statuses and (old_status is None or old_status not in active_statuses):
            await client.mongodb.update_fsub_status(user_id, channel_id, "joined")
            await client.mongodb.add_channel_user(channel_id, user_id)
            
            # Mark join request as approved if exists
            if await client.mongodb.has_submitted_join_request(user_id, channel_id):
                await client.mongodb.update_join_request_status(user_id, channel_id, "approved")
                
        # User left/banned - old_status is active, new_status is None/inactive
        elif old_status in active_statuses and (new_status is None or new_status not in active_statuses):
            # We can't distinguish between left and banned from the update event
            # So we treat both as "left" and let the force sub system handle it
            await client.mongodb.update_fsub_status(user_id, channel_id, "left")
            await client.mongodb.remove_channel_user(channel_id, user_id)
            
            # Clean up join request
            if await client.mongodb.has_submitted_join_request(user_id, channel_id):
                await client.mongodb.remove_join_request(user_id, channel_id)
                
        # Handle specific banned status if Telegram provides it
        elif new_status == ChatMemberStatus.BANNED:
            await client.mongodb.update_fsub_status(user_id, channel_id, "banned")
            await client.mongodb.remove_channel_user(channel_id, user_id)
            
            # Clean up join request
            if await client.mongodb.has_submitted_join_request(user_id, channel_id):
                await client.mongodb.remove_join_request(user_id, channel_id)
                
        # Handle restricted status - user still in channel but limited
        elif new_status == ChatMemberStatus.RESTRICTED:
            await client.mongodb.update_fsub_status(user_id, channel_id, "restricted")
            await client.mongodb.add_channel_user(channel_id, user_id)
            
    except Exception as e:
        client.LOGGER(__name__, client.name).error(f"Member update error: {user_id} in {channel_id}: {e}")


        
